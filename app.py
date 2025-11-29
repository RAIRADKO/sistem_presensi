from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file, Response
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
import cv2
import face_recognition
import numpy as np
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database and face recognition
db = Database()
face_recog = FaceRecognition()

# Global variable untuk menyimpan frame kamera
camera = None
face_samples = []
current_mahasiswa_id = None

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
    global face_samples, current_mahasiswa_id, camera
    
    # Reset dan tutup kamera yang mungkin masih terbuka
    if camera is not None:
        try:
            camera.release()
        except:
            pass
        camera = None
    
    face_samples = []  # Reset samples
    current_mahasiswa_id = id
    
    mahasiswa = db.execute_query("SELECT * FROM mahasiswa WHERE id = %s", (id,))
    if not mahasiswa:
        flash('Mahasiswa tidak ditemukan!', 'error')
        return redirect(url_for('mahasiswa'))
    
    return render_template('daftar_wajah.html', mahasiswa=mahasiswa[0])

def gen_frames():
    """Generator untuk streaming video"""
    global camera, face_samples
    
    try:
        # Tutup kamera jika sudah terbuka
        if camera is not None:
            camera.release()
        
        # Buka kamera baru
        camera = cv2.VideoCapture(0)
        
        if not camera.isOpened():
            print("Error: Cannot open camera")
            # Generate error frame
            error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(error_frame, 'Camera Error', (200, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            ret, buffer = cv2.imencode('.jpg', error_frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            return
        
        # Set camera properties untuk memastikan format yang benar
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        
        # Warm up camera
        for _ in range(5):
            camera.read()
        
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame")
                break
            
            try:
                # Pastikan frame adalah BGR 8-bit
                if len(frame.shape) == 2:  # Grayscale
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] == 4:  # BGRA
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Konversi ke uint8 jika belum
                frame = frame.astype(np.uint8)
                
                # Pastikan contiguous
                frame = np.ascontiguousarray(frame)
                
                # Detect faces untuk menampilkan rectangle
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_frame = np.ascontiguousarray(rgb_frame)
                
                face_locations = face_recognition.face_locations(rgb_frame, model="hog")
                
                # Draw rectangles
                for (top, right, bottom, left) in face_locations:
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 3)
                    cv2.putText(frame, 'Wajah Terdeteksi', (left, top - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                # Display sample count
                cv2.putText(frame, f'Sampel: {len(face_samples)}/5', (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                if len(face_locations) == 0:
                    cv2.putText(frame, 'Tidak ada wajah terdeteksi', (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
                elif len(face_locations) > 1:
                    cv2.putText(frame, 'Terdeteksi > 1 wajah!', (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
            except Exception as e:
                print(f"Error processing frame: {e}")
                import traceback
                traceback.print_exc()
                # Tampilkan error pada frame
                cv2.putText(frame, f'Error: {str(e)[:40]}', (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # Encode frame
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("Failed to encode frame")
                break
                
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
    except Exception as e:
        print(f"Error in gen_frames: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if camera is not None:
            camera.release()

@app.route('/video-feed')
@login_required
def video_feed():
    """Route untuk streaming video"""
    return Response(gen_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/capture-sample', methods=['POST'])
@login_required
@admin_required
def capture_sample():
    """Capture satu sampel wajah"""
    global camera, face_samples
    
    try:
        if camera is None or not camera.isOpened():
            return jsonify({'success': False, 'message': 'Kamera tidak tersedia'})
        
        success, frame = camera.read()
        if not success:
            return jsonify({'success': False, 'message': 'Gagal mengambil frame'})
        
        # Pastikan frame adalah BGR 8-bit
        if len(frame.shape) == 2:  # Grayscale
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.shape[2] == 4:  # BGRA
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        
        # Konversi ke uint8 jika belum
        frame = frame.astype(np.uint8)
        
        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Pastikan rgb_frame adalah contiguous array
        rgb_frame = np.ascontiguousarray(rgb_frame)
        
        # Find faces dengan model yang lebih cepat
        face_locations = face_recognition.face_locations(rgb_frame, model="hog", number_of_times_to_upsample=1)
        
        if len(face_locations) == 0:
            return jsonify({'success': False, 'message': 'Wajah tidak terdeteksi! Pastikan wajah terlihat jelas.'})
        
        if len(face_locations) > 1:
            return jsonify({'success': False, 'message': 'Terdeteksi lebih dari 1 wajah! Pastikan hanya 1 orang di depan kamera.'})
        
        # Get face encodings
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations, num_jitters=1)
        
        if len(face_encodings) == 0:
            return jsonify({'success': False, 'message': 'Gagal mengekstrak fitur wajah!'})
        
        # Add sample
        face_samples.append(face_encodings[0])
        
        return jsonify({
            'success': True,
            'message': f'Sampel {len(face_samples)}/5 berhasil diambil',
            'samples_count': len(face_samples)
        })
        
    except Exception as e:
        print(f"Error in capture_sample: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/save-face/<int:id>', methods=['POST'])
@login_required
@admin_required
def save_face(id):
    """Simpan face encoding ke database"""
    global face_samples, camera
    
    try:
        if len(face_samples) < 5:
            return jsonify({'success': False, 'message': 'Sampel belum cukup! Minimal 5 sampel.'})
        
        # Calculate average encoding
        avg_encoding = np.mean(face_samples, axis=0)
        encoding_list = avg_encoding.tolist()
        
        # Save to database
        db.execute_update(
            "UPDATE mahasiswa SET face_encoding = %s WHERE id = %s",
            (json.dumps(encoding_list), id)
        )
        
        # Log activity
        mahasiswa = db.execute_query("SELECT * FROM mahasiswa WHERE id = %s", (id,))[0]
        db.execute_insert(
            "INSERT INTO log (user_id, activity) VALUES (%s, %s)",
            (session['user_id'], f"Mendaftarkan wajah: {mahasiswa['nama']} ({mahasiswa['nim']})")
        )
        
        # Reload face encodings
        face_recog.load_face_encodings_from_db(db)
        
        # Reset samples
        face_samples = []
        
        # Release camera
        if camera is not None:
            camera.release()
            camera = None
        
        return jsonify({'success': True, 'message': 'Wajah berhasil didaftarkan!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/cancel-capture/<int:id>')
@login_required
@admin_required
def cancel_capture(id):
    """Cancel face capture and release camera"""
    global camera, face_samples
    
    face_samples = []
    if camera is not None:
        camera.release()
        camera = None
    
    return redirect(url_for('mahasiswa'))

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