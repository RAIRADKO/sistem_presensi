// JavaScript untuk interaksi dengan sistem presensi

document.addEventListener('DOMContentLoaded', function() {
    // Tombol start presensi
    const startPresensiBtn = document.getElementById('start-presensi');
    if (startPresensiBtn) {
        startPresensiBtn.addEventListener('click', function() {
            startPresensi();
        });
    }
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

function startPresensi() {
    // Buka window baru untuk presensi
    const presensiWindow = window.open('/api/start-presensi', 'Presensi', 
        'width=800,height=600,menubar=no,toolbar=no,location=no');
    
    if (!presensiWindow) {
        alert('Popup diblokir! Izinkan popup untuk sistem presensi.');
    }
}

// Utility function untuk format tanggal
function formatDate(date) {
    const options = { 
        year: 'numeric', 
        month: '2-digit', 
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    };
    return new Date(date).toLocaleDateString('id-ID', options);
}

// Utility function untuk format confidence score
function formatConfidence(score) {
    if (!score) return '-';
    const percentage = (score * 100).toFixed(2);
    return percentage + '%';
}