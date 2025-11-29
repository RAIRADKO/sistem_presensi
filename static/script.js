// JavaScript untuk interaksi dengan sistem presensi

document.addEventListener('DOMContentLoaded', function() {
    // Tombol daftar wajah
    const captureButtons = document.querySelectorAll('.capture-face');
    captureButtons.forEach(button => {
        button.addEventListener('click', function() {
            const mahasiswaId = this.dataset.id;
            const mahasiswaNama = this.dataset.nama;
            
            if (confirm(`Mulai proses pengambilan wajah untuk ${mahasiswaNama}?`)) {
                captureFace(mahasiswaId);
            }
        });
    });

    // Tombol start presensi
    const startPresensiBtn = document.getElementById('start-presensi');
    if (startPresensiBtn) {
        startPresensiBtn.addEventListener('click', function() {
            startPresensi();
        });
    }
});

function captureFace(mahasiswaId) {
    fetch(`/api/capture-face/${mahasiswaId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Wajah berhasil didaftarkan!');
            location.reload();
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Terjadi kesalahan saat mendaftarkan wajah');
    });
}

function startPresensi() {
    // Buka window baru untuk presensi
    const presensiWindow = window.open('/api/start-presensi', 'Presensi', 
        'width=800,height=600,menubar=no,toolbar=no,location=no');
    
    if (!presensiWindow) {
        alert('Popup diblokir! Izinkan popup untuk sistem presensi.');
    }
}