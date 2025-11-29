import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime
from config import Config

class Database:
    def __init__(self):
        config = Config()
        self.host = config.DB_HOST
        self.user = config.DB_USER
        self.password = config.DB_PASSWORD
        self.database = config.DB_NAME
        self.connection = None
        self.connect()
        self.init_database()

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            print("Database connected successfully")
        except Error as e:
            print(f"Error connecting to database: {e}")

    def init_database(self):
        try:
            cursor = self.connection.cursor()
            
            # Create tables if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    role ENUM('admin', 'operator') NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mahasiswa (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nim VARCHAR(20) UNIQUE NOT NULL,
                    nama VARCHAR(100) NOT NULL,
                    jurusan VARCHAR(50) NOT NULL,
                    face_encoding LONGTEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS presensi (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    mahasiswa_id INT NOT NULL,
                    waktu DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tipe ENUM('masuk', 'keluar') NOT NULL,
                    confidence FLOAT,
                    FOREIGN KEY (mahasiswa_id) REFERENCES mahasiswa(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    activity TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Insert default admin user if not exists
            cursor.execute('SELECT COUNT(*) FROM users')
            if cursor.fetchone()[0] == 0:
                import bcrypt
                hashed_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
                cursor.execute(
                    'INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
                    ('admin', hashed_password.decode('utf-8'), 'admin')
                )
            
            self.connection.commit()
            cursor.close()
            
        except Error as e:
            print(f"Error initializing database: {e}")

    def execute_query(self, query, params=None):
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Error as e:
            print(f"Error executing query: {e}")
            return None

    def execute_insert(self, query, params=None):
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            self.connection.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return last_id
        except Error as e:
            print(f"Error executing insert: {e}")
            return None

    def execute_update(self, query, params=None):
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            self.connection.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
        except Error as e:
            print(f"Error executing update: {e}")
            return None