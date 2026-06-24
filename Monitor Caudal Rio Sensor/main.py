import os
import sys
import logging
import asyncio
import threading
import sqlite3
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import List, Dict, Set

from fastapi import FastAPI
import uvicorn
import joblib
import lgpio
import httpx

from core.database import init_database
from core.config import load_config
from hardware.sensor import read_sensor_pwm
from ai.engine import train_model_with_storm_simulator, run_ai_inference
from api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("RiverSystemAI")
DB_FILE = "sistema_rios.db"

@asynccontextmanager
async def lifespan(app: "RiverMonitorAI"):
    """Instrumenta de forma elástica las sub-rutinas en background y gestiona la liberación del bus GPIO."""
    app.bg_tasks.append(asyncio.create_task(app._sensor_async_worker()))
    app.bg_tasks.append(asyncio.create_task(app._cloud_watchdog_worker()))
    app.bg_tasks.append(asyncio.create_task(app._aws_sync_worker()))
    logger.info("SISTEMA: Ciclo de vida asíncrono inicializado.")
    yield
    for task in app.bg_tasks: task.cancel()
    if app.lgpio_handle is not None:
        try: lgpio.gpiochip_close(app.lgpio_handle)
        except Exception: pass

class RiverMonitorAI(FastAPI):
    """Núcleo operativo distribuido para la orquestación IoT en el borde bajo arquitectura modular."""
    
    def __init__(self, config_path: str, *args, **kwargs):
        super().__init__(lifespan=lifespan, *args, **kwargs)
        base_path = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_path, config_path)
        self.model_path = os.path.join(base_path, "modelo_caudal.pkl")
        self.db_path = os.path.join(base_path, DB_FILE)
        
        # Estructuras de control mutuo para aislamiento de contextos multihilo
        self.model_lock = asyncio.Lock()
        self.config_lock = asyncio.Lock()
        self.db_lock = threading.Lock()  
        
        self.sensor_name = "Sensor_Local_MB1010"
        self.historico_por_estacion: Dict[str, List[dict]] = {self.sensor_name: []}
        self.window_size = 60  
        self.config = load_config(self.config_path, self.sensor_name)
        self.saturacion_suelo = 0.20  
        
        self.cloud_lluvia_prevista_6h = 0.0
        self.cloud_caudal_arriba_m3s = 0.0
        self.ultima_conexion_cloud = datetime.now()
        self.last_aws_push = datetime.now()
        self.modo_cloud_caido = False  
        
        self.log_acciones_sistema: List[str] = []
        self.max_debug_lines = 150
        self.active_connections: Set[any] = set()
        self.bg_tasks: List[asyncio.Task] = []
        
        init_database(self.db_path, self.db_lock)
        try: self.ai_model = joblib.load(self.model_path)
        except Exception: self.ai_model = None
        if self.ai_model is None: self.ai_model = train_model_with_storm_simulator(self.model_path)
        
        self.lgpio_handle = None
        if not self.config["test_mode"]:
            try:
                self.lgpio_handle = lgpio.gpiochip_open(0)
                lgpio.gpio_claim_input(self.lgpio_handle, self.config["pin_pwm"])
            except Exception: self.config["test_mode"] = True

    def _registrar_accion(self, mensaje: str):
        """Escribe una línea formateada en los logs del sistema y mantiene el buffer circular de auditoría."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        logger.info(mensaje)
        self.log_acciones_sistema.append(f"[{timestamp}] {mensaje}")
        if len(self.log_acciones_sistema) > self.max_debug_lines: self.log_acciones_sistema.pop(0)

    async def broadcast_telemetry(self, lectura_dict: dict):
        """Distribuye la telemetría normalizada hacia todos los sockets dúplex remotos activos."""
        if not self.active_connections: return
        acciones_invertidas = list(reversed(self.log_acciones_sistema[-8:]))
        async with self.config_lock: altura_sensor_fija = self.config["altura_sensor_m"]
        payload = {
            "timestamp": lectura_dict["timestamp"], "caudal": lectura_dict["value"],
            "distancia_m": lectura_dict["distancia_m"], "altura_agua_m": lectura_dict["altura_agua_m"],
            "riesgo": lectura_dict["ia_prediction"]["riesgo"], "probabilidad": int(lectura_dict["ia_prediction"]["probabilidad"] * 100),
            "logs_html": "".join([f"<div class='small text-monospace border-bottom py-1'>{l}</div>" for l in acciones_invertidas]),
            "meta_saturacion": round(self.saturacion_suelo * 100, 1),
            "meta_lluvia_cloud": self.cloud_lluvia_prevista_6h if not self.modo_cloud_caido else "⚠️ DESCONECTADO",
            "meta_arriba_cloud": self.cloud_caudal_arriba_m3s if not self.modo_cloud_caido else 0.00,
            "meta_altura_sensor_fija": altura_sensor_fija
        }
        for connection in list(self.active_connections):
            try: await connection.send_json(payload)
            except Exception: self.active_connections.discard(connection)

    async def _sensor_async_worker(self):
        """Loop asíncrono principal dedicado a la ingesta regular y persistencia atómica en SQLite WAL."""
        while True:
            caudal, dist_m, alt_m = await read_sensor_pwm(self)
            if caudal is not None:
                nueva_lectura = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "station": self.sensor_name, "value": caudal, "distancia_m": dist_m, "altura_agua_m": alt_m}
                hist = self.historico_por_estacion[self.sensor_name]; hist.append(nueva_lectura)
                if len(hist) > self.window_size: hist.pop(0)
                prediccion = await run_ai_inference(self, hist); nueva_lectura["ia_prediction"] = prediccion
                with self.db_lock:
                    try:
                        conn = sqlite3.connect(self.db_path); cursor = conn.cursor()
                        cursor.execute("INSERT INTO telemetria_rios (timestamp, estacion, caudal, distancia, altura_agua, riesgo_ia, probabilidad, lluvia_cloud, caudal_arriba_cloud) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", (nueva_lectura["timestamp"], nueva_lectura["station"], caudal, dist_m, alt_m, prediccion["riesgo"], prediccion["probabilidad"], self.cloud_lluvia_prevista_6h, self.cloud_caudal_arriba_m3s))
                        conn.commit(); conn.close()
                    except Exception: pass
                await self.broadcast_telemetry(nueva_lectura)
            async with self.config_lock: intervalo = self.config["interval"]
            await asyncio.sleep(intervalo)

    async def _aws_sync_worker(self):
        """Bucle orquestador de transacciones WAN encargado de la sincronización asíncrona bidireccional con AWS."""
        last_fetch = datetime.now() - timedelta(minutes=15)
        while True:
            ahora = datetime.now()
            async with self.config_lock:
                aws_fetch_url = self.config["aws_fetch_url"]; aws_push_url = self.config["aws_push_url"]
                
            if ahora - last_fetch >= timedelta(minutes=15):
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(aws_fetch_url, params={"station": self.sensor_name})
                        if response.status_code == 200:
                            data = response.json()
                            self.cloud_lluvia_prevista_6h = float(data.get("lluvia_prevista_6h_mm", 0.0))
                            self.cloud_caudal_arriba_m3s = float(data.get("caudal_aguas_arriba_m3s", 0.0))
                            self.ultima_conexion_cloud = ahora; last_fetch = ahora
                except Exception: pass

            if ahora - self.last_aws_push >= timedelta(hours=1):
                self.last_aws_push = ahora 
                un_hora_atras = (ahora - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                avg_caudal = None
                with self.db_lock:
                    try:
                        conn = sqlite3.connect(self.db_path); cursor = conn.cursor()
                        cursor.execute("SELECT AVG(caudal) FROM telemetria_rios WHERE timestamp >= ? AND estacion = ?;", (un_hora_atras, self.sensor_name))
                        res = cursor.fetchone()
                        if res and res[0] is not None: avg_caudal = float(res[0])
                        conn.close()
                    except Exception: pass

                if avg_caudal is not None:
                    try:
                        payload = {"timestamp_envio": ahora.strftime("%Y-%m-%d %H:%M:%S"), "estacion": self.sensor_name, "caudal_medio_60min": round(avg_caudal, 2)}
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            res_push = await client.post(aws_push_url, json=payload)
                            if res_push.status_code in [200, 201]: self.ultima_conexion_cloud = ahora
                    except Exception: pass
            await asyncio.sleep(30)

    async def _cloud_watchdog_worker(self):
        """Monitorea el latido del enlace WAN y activa de forma atómica políticas locales de aislamiento."""
        while True:
            await asyncio.sleep(15)
            if datetime.now() - self.ultima_conexion_cloud > timedelta(minutes=5):
                if not self.modo_cloud_caido: self.modo_cloud_caido = True; self._registrar_accion("ALERTA DE RED: Conexión Cloud perdida.")
            else:
                if self.modo_cloud_caido: self.modo_cloud_caido = False; self._registrar_accion("SISTEMA: Enlace Cloud recuperado.")

app = RiverMonitorAI(config_path="config.xml")
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)