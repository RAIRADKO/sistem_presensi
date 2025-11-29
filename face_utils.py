import cv2
import face_recognition
import numpy as np
import json
from typing import List, Tuple, Optional
import os
from datetime import datetime
from config import Config

class FaceRecognition:
    def __init__(self):
        config = Config()
        self.known_face_encodings = []
        self.known_face_ids = []
        self.known_face_data = []
        self.threshold = config.FACE_RECOGNITION_THRESHOLD
        
    def load_face_encodings_from_db(self, db):
        """Memuat encoding wajah dari database"""
        try:
            results = db.execute_query(
                "SELECT id, nim, nama, face_encoding FROM mahasiswa WHERE face_encoding IS NOT NULL"
            )
            
            self.known_face_encodings = []
            self.known_face_ids = []
            self.known_face_data = []
            
            for row in results:
                try:
                    encoding = json.loads(row['face_encoding'])
                    self.known_face_encodings.append(np.array(encoding))
                    self.known_face_ids.append(row['id'])
                    self.known_face_data.append({
                        'id': row['id'],
                        'nim': row['nim'],
                        'nama': row['nama']
                    })
                except Exception as e:
                    print(f"Error loading encoding for {row['nama']}: {e}")
            
            print(f"Loaded {len(self.known_face_encodings)} face encodings")
            
        except Exception as e:
            print(f"Error loading face encodings from database: {e}")

    def preprocess_frame(self, frame):
        """Preprocess frame untuk memastikan format yang benar"""
        try:
            # Pastikan frame adalah numpy array
            if not isinstance(frame, np.ndarray):
                raise ValueError("Frame must be a numpy array")
            
            # Cek dimensi frame
            if len(frame.shape) == 2:  # Grayscale
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif len(frame.shape) == 3:
                if frame.shape[2] == 4:  # BGRA
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                elif frame.shape[2] != 3:  # Bukan BGR
                    raise ValueError(f"Unsupported number of channels: {frame.shape[2]}")
            else:
                raise ValueError(f"Unsupported frame shape: {frame.shape}")
            
            # Pastikan tipe data uint8
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)
            
            # Pastikan contiguous array
            frame = np.ascontiguousarray(frame)
            
            return frame
            
        except Exception as e:
            print(f"Error in preprocess_frame: {e}")
            raise

    def capture_face_encoding(self, num_samples=5) -> Optional[List[float]]:
        """Mengambil sampel wajah dan menghasilkan encoding rata-rata"""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Cannot open camera")
            return None
        
        # Set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        encodings = []
        samples_taken = 0
        
        print("Starting face capture... Press 'q' to quit, 'c' to capture")
        
        while samples_taken < num_samples:
            ret, frame = cap.read()
            if not ret:
                print("Error: Cannot read frame")
                break
            
            try:
                # Preprocess frame
                frame = self.preprocess_frame(frame)
                
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_frame = np.ascontiguousarray(rgb_frame)
                
                # Find faces
                face_locations = face_recognition.face_locations(rgb_frame, model="hog")
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                # Draw rectangles around faces
                for (top, right, bottom, left) in face_locations:
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                
                # Display instructions
                cv2.putText(frame, f"Samples: {samples_taken}/{num_samples}", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, "Press 'c' to capture, 'q' to quit", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                cv2.imshow('Face Enrollment', frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('c') and len(face_encodings) > 0:
                    encodings.append(face_encodings[0])
                    samples_taken += 1
                    print(f"Sample {samples_taken} captured")
                    
            except Exception as e:
                print(f"Error processing frame: {e}")
                cv2.putText(frame, f"Error: {str(e)[:30]}", 
                           (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                cv2.imshow('Face Enrollment', frame)
                cv2.waitKey(1)
        
        cap.release()
        cv2.destroyAllWindows()
        
        if len(encodings) > 0:
            # Calculate average encoding
            avg_encoding = np.mean(encodings, axis=0)
            return avg_encoding.tolist()
        
        return None

    def recognize_face(self, frame) -> Tuple[Optional[int], Optional[str], Optional[str], float]:
        """Mengenali wajah dalam frame"""
        if len(self.known_face_encodings) == 0:
            return None, None, None, 0.0
        
        try:
            # Preprocess frame
            frame = self.preprocess_frame(frame)
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame = np.ascontiguousarray(rgb_frame)
            
            # Find faces
            face_locations = face_recognition.face_locations(rgb_frame, model="hog")
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if len(face_encodings) == 0:
                return None, None, None, 0.0
            
            # Compare with known faces
            face_encoding = face_encodings[0]
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=self.threshold)
            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            
            best_match_index = np.argmin(face_distances)
            
            if matches[best_match_index]:
                confidence = 1 - face_distances[best_match_index]
                face_data = self.known_face_data[best_match_index]
                return face_data['id'], face_data['nim'], face_data['nama'], confidence
            
            return None, None, None, 0.0
            
        except Exception as e:
            print(f"Error in recognize_face: {e}")
            return None, None, None, 0.0

    def run_attendance(self, db, callback=None):
        """Menjalankan sistem presensi real-time"""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Cannot open camera")
            return
        
        # Set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        last_attendance = {}
        attendance_cooldown = 5  # seconds
        
        print("Starting attendance system... Press 'q' to quit")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Cannot read frame")
                break
            
            try:
                # Preprocess frame
                frame = self.preprocess_frame(frame)
                
                # Recognize face
                mahasiswa_id, nim, nama, confidence = self.recognize_face(frame)
                
                current_time = datetime.now()
                
                # Draw results on frame
                if mahasiswa_id:
                    # Check cooldown
                    if mahasiswa_id in last_attendance:
                        time_diff = (current_time - last_attendance[mahasiswa_id]).total_seconds()
                        if time_diff < attendance_cooldown:
                            status = f"Cooldown: {attendance_cooldown - int(time_diff)}s"
                            color = (0, 255, 255)  # Yellow
                        else:
                            status = "Recognized - Press 's' to save"
                            color = (0, 255, 0)  # Green
                    else:
                        status = "Recognized - Press 's' to save"
                        color = (0, 255, 0)  # Green
                    
                    cv2.putText(frame, f"NIM: {nim}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    cv2.putText(frame, f"Nama: {nama}", (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    cv2.putText(frame, f"Confidence: {confidence:.2f}", (10, 90), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    cv2.putText(frame, status, (10, 120), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    
                    # Save attendance when 's' is pressed
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('s') and (mahasiswa_id not in last_attendance or 
                                          (current_time - last_attendance[mahasiswa_id]).total_seconds() >= attendance_cooldown):
                        
                        # Determine attendance type
                        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                        today_presensi = db.execute_query(
                            "SELECT tipe FROM presensi WHERE mahasiswa_id = %s AND waktu >= %s ORDER BY waktu DESC LIMIT 1",
                            (mahasiswa_id, today_start)
                        )
                        
                        if today_presensi and today_presensi[0]['tipe'] == 'masuk':
                            tipe = 'keluar'
                        else:
                            tipe = 'masuk'
                        
                        # Save to database
                        db.execute_insert(
                            "INSERT INTO presensi (mahasiswa_id, tipe, confidence) VALUES (%s, %s, %s)",
                            (mahasiswa_id, tipe, confidence)
                        )
                        
                        last_attendance[mahasiswa_id] = current_time
                        
                        if callback:
                            callback(nim, nama, tipe, confidence)
                        
                        print(f"Presensi {tipe} dicatat untuk {nama}")
                    
                else:
                    cv2.putText(frame, "Wajah tidak dikenali", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.putText(frame, "Press 'q' to quit", (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                cv2.imshow('Presensi System', frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
            except Exception as e:
                print(f"Error in attendance loop: {e}")
                cv2.putText(frame, f"Error: {str(e)[:30]}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                cv2.imshow('Presensi System', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        cap.release()
        cv2.destroyAllWindows()