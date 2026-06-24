import sqlite3
import threading

def init_database(db_path: str, db_lock: threading.Lock):
    """
    Inicializa el esquema relacional local e instrumenta el motor SQLite.
    
    Aplica configuraciones a nivel de pragma para optimizar la concurrencia
    y garantizar la integridad transaccional bajo cargas continuas de I/O.

    Args:
        db_path (str): Ruta absoluta hacia el archivo binario de la base de datos.
        db_lock (threading.Lock): Primitiva de exclusión mutua para control de accesos concurrentes.
    """
    with db_lock:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # El modo WAL permite escrituras atómicas sin bloquear operaciones concurrentes de lectura
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetria_rios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                estacion TEXT,
                caudal REAL,
                distancia REAL,
                altura_agua REAL,
                riesgo_ia TEXT,
                probabilidad REAL,
                lluvia_cloud REAL,
                caudal_arriba_cloud REAL,
                inundacion_real INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()