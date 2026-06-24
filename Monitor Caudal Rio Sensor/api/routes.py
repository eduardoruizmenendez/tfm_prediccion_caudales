import os
import sys
import sqlite3
import threading
import subprocess
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
import joblib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from core.config import save_config_to_xml

router = APIRouter()

def _read_template(base_path: str, filename: str) -> str:
    """Carga un recurso estático puro en texto plano desde el sistema de archivos local."""
    path = os.path.join(base_path, "templates", filename)
    with open(path, "r", encoding="utf-8") as f: return f.read()

@router.get("/")
async def root_redirect(): 
    return RedirectResponse(url="/dashboard")

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return HTMLResponse(content=_read_template(base, "dashboard.html"))

@router.get("/audit", response_class=HTMLResponse)
async def get_audit_page():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return HTMLResponse(content=_read_template(base, "audit.html"))

@router.get("/settings", response_class=HTMLResponse)
async def get_settings_page(request: Request):
    app = request.app
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    async with app.config_lock:
        interval = app.config["interval"]; test_mode = app.config["test_mode"]
        max_caudal = app.config["max_caudal"]; altura_sensor_m = app.config["altura_sensor_m"]
        pin_pwm = app.config["pin_pwm"]
        aws_fetch_url = app.config["aws_fetch_url"]; aws_push_url = app.config["aws_push_url"]
        
    html = _read_template(base, "settings.html")
    html = html.replace("__INTERVAL__", str(interval)).replace("__ALTURA__", str(altura_sensor_m)).replace("__CAUDAL__", str(max_caudal))
    html = html.replace("__PIN_PWM__", str(pin_pwm)).replace("__AWS_FETCH__", str(aws_fetch_url)).replace("__AWS_PUSH__", str(aws_push_url))
    html = html.replace("__SELECT_FISICO__", "selected" if not test_mode else "").replace("__SELECT_SIMULADO__", "selected" if test_mode else "")
    return HTMLResponse(content=html)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    app = websocket.app; await websocket.accept(); app.active_connections.add(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: pass
    finally: app.active_connections.discard(websocket)

@router.post("/update-config")
async def update_remote_config(request: Request, payload: dict = Body(...)):
    app = request.app
    try:
        interval = int(payload.get("polling_interval_seconds", 1))
        test_mode = bool(payload.get("test_mode", False))
        max_caudal = float(payload.get("max_caudal_calibracion", 10.0))
        altura_sensor_m = float(payload.get("altura_sensor_instalado_metros", 3.81))
        pin_pwm = int(payload.get("pin_pwm_gpio", 23))
        aws_fetch_url = str(payload.get("aws_fetch_url", ""))
        aws_push_url = str(payload.get("aws_push_url", ""))
        
        async with app.config_lock:
            save_config_to_xml(app.config_path, interval, test_mode, max_caudal, altura_sensor_m, pin_pwm, aws_fetch_url, aws_push_url)
            app.config.update({
                "interval": interval, "test_mode": test_mode, "max_caudal": max_caudal, "altura_sensor_m": altura_sensor_m,
                "pin_pwm": pin_pwm, "aws_fetch_url": aws_fetch_url, "aws_push_url": aws_push_url
            })
        app._registrar_accion("CONFIG: config.xml actualizado en caliente.")
        return {"status": "success", "message": "Configuración aplicada."}
    except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/mark-flood")
async def mark_flood_event(request: Request, payload: dict = Body(...)):
    app = request.app
    with app.db_lock:
        try:
            conn = sqlite3.connect(app.db_path); cursor = conn.cursor()
            cursor.execute("UPDATE telemetria_rios SET inundacion_real = ? WHERE timestamp BETWEEN ? AND ?;", (int(payload.get("hubo_inundacion", 1)), payload.get("timestamp_inicio"), payload.get("timestamp_fin")))
            conn.commit(); conn.close()
        except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return {"status": "success", "message": "Registros auditados."}

def ejecutor_reinicio_autonomo():
    import time
    time.sleep(1.5)
    script_actual = os.path.abspath(sys.argv[0])
    subprocess.Popen([sys.executable, script_actual], close_fds=True, start_new_session=True)
    os._exit(0)

@router.post("/restart-system")
async def restart_system_endpoint(request: Request):
    app = request.app
    app._registrar_accion("WATCHDOG: Reiniciando subsistemas.")
    threading.Thread(target=ejecutor_reinicio_autonomo, daemon=True).start()
    return {"status": "success", "message": "Servidor reiniciando."}

@router.post("/retrain")
async def retrain_model_from_db(request: Request):
    app = request.app; X_real, y_real = [], []
    with app.db_lock:
        try:
            conn = sqlite3.connect(app.db_path); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT * FROM telemetria_rios ORDER BY id DESC LIMIT 3000;"); filas = cursor.fetchall(); conn.close()
        except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    if len(filas) < 30: return JSONResponse(status_code=400, content={"status": "error", "message": "Muestras de campo insuficientes."})
    filas = list(reversed(filas)); caudales = [float(f["caudal"]) for f in filas]; suelo_sim = 0.30
    for i in range(2, len(filas)):
        c_act = caudales[i]; vel = c_act - caudales[i-1]; acc = vel - (caudales[i-1] - caudales[i-2])
        med_movil = float(np.mean(caudales[max(0, i-5):i+1]))
        suelo_sim = min(suelo_sim + (c_act * 0.0005), 1.0) if vel > 0 else max(suelo_sim - 0.0001, 0.05)
        label = int(filas[i]["inundacion_real"])
        if label == 0 and c_act > 4.2: label = 1 
        X_real.append([c_act, vel, acc, med_movil, suelo_sim, float(filas[i]["lluvia_cloud"]), float(filas[i]["caudal_arriba_cloud"])])
        y_real.append(label)
    async with app.model_lock:
        try:
            nuevo_bosque = RandomForestClassifier(n_estimators=80, max_depth=5, random_state=42); nuevo_bosque.fit(np.array(X_real), np.array(y_real))
            joblib.dump(nuevo_bosque, app.model_path); app.ai_model = nuevo_bosque
            app._registrar_accion("IA: Random Forest optimizado en caliente.")
            return {"status": "success", "message": "Modelo entrenado con éxito."}
        except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/debug-sensor")
async def get_debug_sensor(request: Request):
    """Retorna los últimos 1000 registros de telemetría de campo puros desde SQLite."""
    app = request.app; medidas = []
    with app.db_lock:
        try:
            conn = sqlite3.connect(app.db_path); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT * FROM telemetria_rios ORDER BY id DESC LIMIT 1000;")
            for fila in cursor.fetchall():
                medidas.append({"timestamp": fila["timestamp"], "estacion": fila["estacion"], "caudal_m3_s": fila["caudal"], "distancia_sensor_m": fila["distancia"], "altura_agua_m": fila["altura_agua"], "riesgo_ia": fila["riesgo_ia"], "probabilidad": fila["probabilidad"]})
            conn.close()
        except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return JSONResponse(content={"historial_medidas": medidas})

# FIXED-1: El alias con guion bajo procesa la llamada pero se oculta del esquema OpenAPI
@router.get("/debug_sensor", include_in_schema=False)
async def get_debug_sensor_alias(request: Request):
    return await get_debug_sensor(request)

@router.get("/predict")
async def get_predictions(request: Request):
    """Muestra el vector de estado de inferencia hidrológica activa retenido en memoria RAM."""
    app = request.app
    return {url: d[-1] for url, d in app.historico_por_estacion.items() if d}

@router.get("/api/historico")
async def get_historico_ventana(request: Request, horas: str = "1.0"):
    """Filtra y extrae series de tiempo agregadas según la ventana horaria solicitada."""
    app = request.app
    try: horas_float = float(horas)
    except ValueError: horas_float = 1.0
    limite = (datetime.now() - timedelta(hours=horas_float)).strftime("%Y-%m-%d %H:%M:%S")
    with app.db_lock:
        try:
            conn = sqlite3.connect(app.db_path); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT timestamp, caudal, distancia, altura_agua, riesgo_ia, probabilidad FROM telemetria_rios WHERE timestamp >= ? AND estacion = ? ORDER BY timestamp ASC;", (limite, app.sensor_name))
            filas = cursor.fetchall(); conn.close()
        except Exception as e: return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    datos = [{"timestamp": f["timestamp"], "caudal": f["caudal"], "distancia_m": f["distancia"], "altura_agua_m": f["altura_agua"], "riesgo": f["riesgo_ia"], "probabilidad": f["probabilidad"]} for f in filas]
    return JSONResponse(content=datos)

# FIXED-2: Captura las llamadas erráticas con trailing slash final ocultándolas de Swagger
@router.get("/api/historico/", include_in_schema=False)
async def get_historico_ventana_trailing(request: Request, horas: str = "1.0"):
    return await get_historico_ventana(request, horas)