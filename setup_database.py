import mysql.connector
from mysql.connector import Error
import bcrypt

def setup_database():
    try:
        # Connect to MySQL server
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password=''  # Sesuaikan dengan password MySQL Anda
        )
        
        if connection.is_connected():
            cursor = connection.cursor()
            
            # Create database
            cursor.execute("CREATE DATABASE IF NOT EXISTS presensi_system")
            print("Database created successfully")
            
            # Use database
            cursor.execute("USE presensi_system")
            
            # Create tables
            tables = [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    role ENUM('admin', 'operator') NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS mahasiswa (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nim VARCHAR(20) UNIQUE NOT NULL,
                    nama VARCHAR(100) NOT NULL,
                    jurusan VARCHAR(50) NOT NULL,
                    face_encoding LONGTEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS presensi (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    mahasiswa_id INT NOT NULL,
                    waktu DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tipe ENUM('masuk','keluar') NOT NULL,
                    confidence FLOAT,
                    FOREIGN KEY (mahasiswa_id) REFERENCES mahasiswa(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    activity TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            ]
            
            for table in tables:
                cursor.execute(table)
            
            # Insert default admin user
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                hashed_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    ('admin', hashed_password.decode('utf-8'), 'admin')
                )
                print("Default admin user created: admin / admin123")
            
            connection.commit()
            print("All tables created successfully")
            
    except Error as e:
        print(f"Error: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    setup_database()