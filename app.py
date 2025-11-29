from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from database import Database
from face_utils import FaceRecognition
import bcrypt
import json
from datetime import datetime, timedelta
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io
import os
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database and face recognition
db = Database()
face_recog = FaceRecognition()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Akses ditolak. Hanya admin yang dapat mengakses halaman ini.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = db.execute_query(
            "SELECT * FROM users WHERE username = %s", (username,)
        )
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user[0]['password'].encode('utf-8')):
            session['user_id'] = user[0]['id']
            session['username'] = user[0]['username']
            session['role'] = user[0]['role']
            
            # Log activity
            db.execute_insert(
                "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
                (user[0]['id'], f"User {username} logged in")
            )
            
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        # Log activity
        db.execute_insert(
            "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
            (session['user_id'], f"User {session['username']} logged out")
        )
    
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get statistics
    total_mahasiswa = db.execute_query("SELECT COUNT(*) as count FROM mahasiswa")[0]['count']
    total_presensi_hari_ini = db.execute_query(
        "SELECT COUNT(*) as count FROM presensi WHERE DATE(waktu) = CURDATE()"
    )[0]['count']
    mahasiswa_dengan_wajah = db.execute_query(
        "SELECT COUNT(*) as count FROM mahasiswa WHERE face_encoding IS NOT NULL"
    )[0]['count']
    
    # Recent attendance
    recent_presensi = db.execute_query('''
        SELECT p.*, m.nim, m.nama 
        FROM presensi p 
        JOIN mahasiswa m ON p.mahasiswa_id = m.id 
        ORDER BY p.waktu DESC 
        LIMIT 10
    ''')
    
    return render_template('dashboard.html',
                         total_mahasiswa=total_mahasiswa,
                         total_presensi=total_presensi_hari_ini,
                         mahasiswa_dengan_wajah=mahasiswa_dengan_wajah,
                         recent_presensi=recent_presensi)

@app.route('/mahasiswa')
@login_required
def mahasiswa():
    mahasiswa_list = db.execute_query("SELECT * FROM mahasiswa ORDER BY nama")
    
    # Add face status
    for m in mahasiswa_list:
        m['has_face'] = m['face_encoding'] is not None
    
    return render_template('mahasiswa.html', mahasiswa_list=mahasiswa_list)

@app.route('/mahasiswa/tambah', methods=['GET', 'POST'])
@login_required
@admin_required
def tambah_mahasiswa():
    if request.method == 'POST':
        nim = request.form['nim']
        nama = request.form['nama']
        jurusan = request.form['jurusan']
        
        try:
            db.execute_insert(
                "INSERT INTO mahasiswa (nim, nama, jurusan) VALUES (%s, %s, %s)",
                (nim, nama, jurusan)
            )
            
            # Log activity
            db.execute_insert(
                "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
                (session['user_id'], f"Menambah mahasiswa: {nama} ({nim})")
            )
            
            flash('Mahasiswa berhasil ditambahkan!', 'success')
            return redirect(url_for('mahasiswa'))
        
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('tambah_mahasiswa.html')

@app.route('/mahasiswa/<int:id>/hapus')
@login_required
@admin_required
def hapus_mahasiswa(id):
    try:
        mahasiswa = db.execute_query("SELECT * FROM mahasiswa WHERE id = %s", (id,))[0]
        db.execute_update("DELETE FROM mahasiswa WHERE id = %s", (id,))
        
        # Log activity
        db.execute_insert(
            "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
            (session['user_id'], f"Menghapus mahasiswa: {mahasiswa['nama']} ({mahasiswa['nim']})")
        )
        
        flash('Mahasiswa berhasil dihapus!', 'success')
    
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('mahasiswa'))

@app.route('/mahasiswa/<int:id>/daftar-wajah')
@login_required
@admin_required
def daftar_wajah(id):
    mahasiswa = db.execute_query("SELECT * FROM mahasiswa WHERE id = %s", (id,))[0]
    return render_template('daftar_wajah.html', mahasiswa=mahasiswa)

@app.route('/api/capture-face/<int:id>', methods=['POST'])
@login_required
@admin_required
def api_capture_face(id):
    try:
        encoding = face_recog.capture_face_encoding(num_samples=5)
        
        if encoding:
            db.execute_update(
                "UPDATE mahasiswa SET face_encoding = %s WHERE id = %s",
                (json.dumps(encoding), id)
            )
            
            # Log activity
            mahasiswa = db.execute_query("SELECT * FROM mahasiswa WHERE id = %s", (id,))[0]
            db.execute_insert(
                "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
                (session['user_id'], f"Mendaftarkan wajah: {mahasiswa['nama']} ({mahasiswa['nim']})")
            )
            
            # Reload face encodings
            face_recog.load_face_encodings_from_db(db)
            
            return jsonify({'success': True, 'message': 'Wajah berhasil didaftarkan!'})
        else:
            return jsonify({'success': False, 'message': 'Gagal mengambil sampel wajah!'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/presensi')
@login_required
def presensi():
    # Load face encodings before starting
    face_recog.load_face_encodings_from_db(db)
    return render_template('presensi.html')

@app.route('/api/start-presensi')
@login_required
def api_start_presensi():
    def attendance_callback(nim, nama, tipe, confidence):
        # This function will be called when attendance is recorded
        print(f"Presensi {tipe} untuk {nama} ({nim}) - Confidence: {confidence}")
    
    face_recog.run_attendance(db, callback=attendance_callback)
    return jsonify({'success': True})

@app.route('/laporan')
@login_required
def laporan():
    # Default: show today's attendance
    tanggal = request.args.get('tanggal', datetime.now().strftime('%Y-%m-%d'))
    
    presensi_data = db.execute_query('''
        SELECT p.*, m.nim, m.nama, m.jurusan
        FROM presensi p 
        JOIN mahasiswa m ON p.mahasiswa_id = m.id 
        WHERE DATE(p.waktu) = %s
        ORDER BY p.waktu DESC
    ''', (tanggal,))
    
    return render_template('laporan.html', presensi_data=presensi_data, tanggal=tanggal)

@app.route('/api/laporan/export-excel')
@login_required
def export_excel():
    tanggal = request.args.get('tanggal', datetime.now().strftime('%Y-%m-%d'))
    
    presensi_data = db.execute_query('''
        SELECT m.nim, m.nama, m.jurusan, p.tipe, p.waktu, p.confidence
        FROM presensi p 
        JOIN mahasiswa m ON p.mahasiswa_id = m.id 
        WHERE DATE(p.waktu) = %s
        ORDER BY p.waktu
    ''', (tanggal,))
    
    # Create DataFrame
    df = pd.DataFrame(presensi_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Presensi_{tanggal}', index=False)
    
    output.seek(0)
    
    # Log activity
    db.execute_insert(
        "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
        (session['user_id'], f"Export Excel laporan presensi tanggal {tanggal}")
    )
    
    return send_file(output, 
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f'presensi_{tanggal}.xlsx')

@app.route('/api/laporan/export-pdf')
@login_required
def export_pdf():
    tanggal = request.args.get('tanggal', datetime.now().strftime('%Y-%m-%d'))
    
    presensi_data = db.execute_query('''
        SELECT m.nim, m.nama, m.jurusan, p.tipe, p.waktu, p.confidence
        FROM presensi p 
        JOIN mahasiswa m ON p.mahasiswa_id = m.id 
        WHERE DATE(p.waktu) = %s
        ORDER BY p.waktu
    ''', (tanggal,))
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Title
    styles = getSampleStyleSheet()
    title = Paragraph(f"Laporan Presensi - {tanggal}", styles['Title'])
    elements.append(title)
    
    # Table data
    table_data = [['NIM', 'Nama', 'Jurusan', 'Tipe', 'Waktu', 'Confidence']]
    
    for presensi in presensi_data:
        table_data.append([
            presensi['nim'],
            presensi['nama'],
            presensi['jurusan'],
            presensi['tipe'],
            presensi['waktu'].strftime('%H:%M:%S'),
            f"{presensi['confidence']:.2f}" if presensi['confidence'] else '-'
        ])
    
    # Create table
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    # Log activity
    db.execute_insert(
        "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
        (session['user_id'], f"Export PDF laporan presensi tanggal {tanggal}")
    )
    
    return send_file(buffer, 
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'presensi_{tanggal}.pdf')

if __name__ == '__main__':
    # Load initial face encodings
    face_recog.load_face_encodings_from_db(db)
    app.run(debug=True, host='0.0.0.0', port=5000)