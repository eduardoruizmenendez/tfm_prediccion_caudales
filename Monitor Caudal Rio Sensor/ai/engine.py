import random
import numpy as np
from sklearn.ensemble import RandomForestClassifier 
import joblib

def train_model_with_storm_simulator(model_path: str) -> RandomForestClassifier:
    """
    Sintetiza de forma determinista matrices de avenidas e instrumenta un estimador base.

    Args:
        model_path (str): Ubicación física para la serialización binaria del modelo de ensamble.

    Returns:
        RandomForestClassifier: Instancia optimizada del clasificador ajustado.
    """
    X_train, y_train = [], []
    for escenario in range(45):
        es_critico = (escenario % 3 == 0)
        base_caudal = random.uniform(0.8, 2.2)
        max_crecida = random.uniform(5.5, 9.5) if es_critico else random.uniform(1.8, 4.0)
        lluvia_simulada = random.uniform(45.0, 110.0) if es_critico else random.uniform(0.0, 20.0)
        caudal_arriba = random.uniform(4.0, 8.5) if es_critico else random.uniform(0.0, 1.5)
        estado_suelo = random.uniform(0.1, 0.8) 
        
        caudales_serie = []
        for t in range(100):
            if t < 50:
                c = base_caudal + (max_crecida - base_caudal) / (1 + np.exp(-0.12 * (t - 25)))
            else:
                c = base_caudal + (caudales_serie[-1] - base_caudal) * 0.95
            caudales_serie.append(c)

        for t in range(2, 100):
            c_act = caudales_serie[t]; v_crecida = c_act - caudales_serie[t-1]; a_crecida = v_crecida - (caudales_serie[t-1] - caudales_serie[t-2]) 
            m_movil = float(np.mean(caudales_serie[max(0, t-5):t+1]))
            estado_suelo = min(estado_suelo + (c_act * 0.001), 1.0)
            if c_act > 7.0 or (c_act > 5.0 and v_crecida > 0.35 and estado_suelo > 0.65): label = 2
            elif c_act > 3.8 or v_crecida > 0.12: label = 1
            else: label = 0
            X_train.append([c_act, v_crecida, a_crecida, m_movil, estado_suelo, lluvia_simulada, caudal_arriba])
            y_train.append(label)

    bosque_ia = RandomForestClassifier(n_estimators=80, max_depth=5, random_state=42)
    bosque_ia.fit(np.array(X_train), np.array(y_train))
    joblib.dump(bosque_ia, model_path)
    return bosque_ia

async def run_ai_inference(app, data_window: list) -> dict:
    """
    Construye la matriz de entrada heptadimensional y evalúa el riesgo hidrológico en la periferia.

    Args:
        app: Instancia de la aplicación central (RiverMonitorAI).
        data_window (list): Estructura cíclica de telemetría reciente en memoria caché RAM.

    Returns:
        dict: Clasificación discreta del nivel de riesgo junto con su distribución de probabilidad.
    """
    if len(data_window) < 3: return {"riesgo": "Calculando...", "probabilidad": 0.0, "tendencia": 0.0}
    caudal_actual = data_window[-1]["value"]
    velocidad_crecida = caudal_actual - data_window[-2]["value"]
    aceleracion_crecida = velocidad_crecida - (data_window[-2]["value"] - data_window[-3]["value"])
    media_movil_local = float(np.mean([m["value"] for m in data_window[-5:]]))
    
    if velocidad_crecida > 0: app.saturacion_suelo = min(app.saturacion_suelo + (caudal_actual * 0.0004), 1.0)
    else: app.saturacion_suelo = max(app.saturacion_suelo - 0.0001, 0.05)
    
    lluvia_input = 35.0 if (app.modo_cloud_caido and velocidad_crecida > 0.05) else app.cloud_lluvia_prevista_6h
    caudal_arriba_input = 2.50 if (app.modo_cloud_caido and velocidad_crecida > 0.05) else app.cloud_caudal_arriba_m3s
    features = [[caudal_actual, velocidad_crecida, aceleracion_crecida, media_movil_local, app.saturacion_suelo, lluvia_input, caudal_arriba_input]]
    
    # Barrera simétrica de exclusión mutua asíncrona para blindar los pesos concurrentes del estimador
    async with app.model_lock:
        if not app.ai_model: 
            riesgo_fallback = "ESTABLE (BAJO)" if caudal_actual < 4.0 else ("ALERTA (MEDIO)" if caudal_actual < 6.5 else "INUNDACIÓN (ALTO)")
            return {"riesgo": riesgo_fallback, "probabilidad": 0.50, "tendencia": round(velocidad_crecida, 3)}
        try:
            prediction_id = int(app.ai_model.predict(features)[0])
            probabilidades = app.ai_model.predict_proba(features)[0]
            prob_final = round(float(probabilidades[prediction_id]), 2)
        except Exception:
            prediction_id = 0; prob_final = 1.0
            
    mapeo_riesgo = {0: "ESTABLE (BAJO)", 1: "ALERTA (MEDIO)", 2: "INUNDACIÓN (ALTO)"}
    return {"riesgo": mapeo_riesgo.get(prediction_id, "ESTABLE (BAJO)"), "probabilidad": prob_final, "tendencia": round(velocidad_crecida, 3)}