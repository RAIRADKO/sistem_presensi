from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import json

@dataclass
class User:
    id: int
    username: str
    password: str
    role: str
    created_at: datetime

@dataclass
class Mahasiswa:
    id: int
    nim: str
    nama: str
    jurusan: str
    face_encoding: Optional[List[float]]
    created_at: datetime
    has_face: bool = False

    def to_dict(self):
        return {
            'id': self.id,
            'nim': self.nim,
            'nama': self.nama,
            'jurusan': self.jurusan,
            'has_face': self.has_face,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

@dataclass
class Presensi:
    id: int
    mahasiswa_id: int
    waktu: datetime
    tipe: str
    confidence: float
    mahasiswa_nama: str = ""
    mahasiswa_nim: str = ""

@dataclass
class Log:
    id: int
    user_id: int
    activity: str
    timestamp: datetime