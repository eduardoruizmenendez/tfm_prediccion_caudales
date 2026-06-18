import os
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
import tensorflow as tf

# Ingesta oficial y nativa de tus utilidades del TFM
from utils_adquisicion_datos import obtener_argumentos_cuenca_y_nivel, hacer_peticion_robusta

# Desactivamos los mensajes informativos innecesarios de TensorFlow para limpiar la consola
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# =========================================================================
# ENTRADA CLI Y CONFIGURACIÓN DINÁMICA DE PRODUCCIÓN
# =========================================================================
# Invocamos la nueva extensión: extrae todo de forma limpia en una sola línea
id_cuenca, parametros, credenciales, nivel_actual = obtener_argumentos_cuenca_y_nivel()

fecha_actual = datetime.now()
fecha_str = fecha_actual.strftime("%Y-%m-%d %H:%M:%S")

print("=====================================================================")
print(f"🔮 MOTOR DE INFERENCIA EN TIEMPO REAL: TRIBUNAL CLOUD")
print(f"🏞️  Cuenca Atómica: {parametros['nombre_legible']}")
print(f"📏 Lectura Sensor (t0): {nivel_actual} m")
print("=====================================================================\n")

# Extraemos las rutas parametrizadas de tu diccionario centralizado
carpeta_modelos = parametros.get("carpeta_modelos", f"data/output/modelos/{id_cuenca}")
ruta_scaler = parametros.get("ruta_scaler", os.path.join(carpeta_modelos, f"scaler_{id_cuenca}.pkl"))
ruta_destino_predicciones = parametros.get("ruta_log_predicciones", f"data/output/predicciones_produccion/{id_cuenca}/historico_predicciones_log.csv")

os.makedirs(os.path.dirname(ruta_destino_predicciones), exist_ok=True)

# =========================================================================
# PRECARGA ESTRATÉGICA DE ARTEFACTOS EN MEMORIA RAM (MLOps Optimizado)
# =========================================================================
print("📦 [1/6 - PRECARGA] Cargando estimadores y escalador en memoria RAM...")

if not os.path.exists(ruta_scaler):
    print(f"❌ Error Crítico: No se encuentra el archivo del escalador en: {ruta_scaler}")
    exit()
scaler = joblib.load(ruta_scaler)

horizontes_abreviados = ['t+1', 't+4', 't+8', 't+12', 't+24']
dict_modelos_xgb = {}
dict_modelos_bilstm = {}

for h in horizontes_abreviados:
    target_str = f"TARGET_{h}"
    ruta_xgb = os.path.join(carpeta_modelos, f"xgboost_{target_str}.pkl")
    ruta_bilstm = os.path.join(carpeta_modelos, f"bilstm_{target_str}.keras")
    
    dict_modelos_xgb[h] = joblib.load(ruta_xgb) if os.path.exists(ruta_xgb) else None
    dict_modelos_bilstm[h] = tf.keras.models.load_model(ruta_bilstm) if os.path.exists(ruta_bilstm) else None

print("   -> 🧠 Estructuras de grafos compiladas. Modelos residentes en RAM con éxito.")

# =========================================================================
# INGESTA DE VARIABLES METEOROLÓGICAS MULTI-API MEDIANTE PETICIONES ROBUSTAS
# =========================================================================
print("\n📡 [2/6 - INGESTA] Consultando APIs meteorológicas en tiempo real...")

tp_t0, p_acum_12h, p_acum_24h = 0.0, 0.0, 0.0
t2m_t0 = parametros.get("aemet_t2m_fallback", 14.5)

# Consumo de las coordenadas dinámicas del fichero de configuración centralizado
lat, lon = parametros.get("openmeteo_lat_lon", (43.10, -4.00))
url_openmeteo = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation&forecast_days=1"

# Invocamos la utilidad de peticiones con reintentos automáticos desarrollada para el TFM
response_om = hacer_peticion_robusta(url_openmeteo, timeout=10)

if response_om is not None:
    try:
        datos_om = response_om.json()
        tp_t0 = float(datos_om["hourly"]["precipitation"][0])
        p_acum_12h = float(np.sum(datos_om["hourly"]["precipitation"][:12]))
        p_acum_24h = float(np.sum(datos_om["hourly"]["precipitation"][:24]))
        print(f"   -> 🌦️  Open-Meteo consultado con éxito. tp: {tp_t0} mm | p_acum_24h: {p_acum_24h} mm")
    except Exception as e:
        print(f"   -> ⚠️ Error al deserializar JSON de Open-Meteo ({e}). Aplicando Fallback (0.0 mm).")
else:
    print("   -> ⚠️ API Open-Meteo caída tras reintentos. Aplicando contingencia basal (0.0 mm).")

print(f"   -> 🌡️  t2m actual parametrizada: {t2m_t0} °C")

# =========================================================================
# RECUPERACIÓN DE LAGS HIDROLÓGICOS ANTECEDENTES (MEMORIA DEL RÍO)
# =========================================================================
print("\n📂 [3/6 - HISTÓRICO] Recuperando registros hidrológicos de control...")

lag_1h, lag_4h, lag_8h, lag_12h, lag_24h = nivel_actual, nivel_actual, nivel_actual, nivel_actual, nivel_actual

if os.path.exists(ruta_destino_predicciones):
    try:
        df_historico_log = pd.read_csv(ruta_destino_predicciones)
        n_registros = len(df_historico_log)
        
        if n_registros >= 1: lag_1h = float(df_historico_log['nivel_sensor_t0'].iloc[-1])
        lag_4h = float(df_historico_log['nivel_sensor_t0'].iloc[-4]) if n_registros >= 4 else nivel_actual
        lag_8h = float(df_historico_log['nivel_sensor_t0'].iloc[-8]) if n_registros >= 8 else nivel_actual
        lag_12h = float(df_historico_log['nivel_sensor_t0'].iloc[-12]) if n_registros >= 12 else nivel_actual
        lag_24h = float(df_historico_log['nivel_sensor_t0'].iloc[-24]) if n_registros >= 24 else nivel_actual
        
        print(f"   -> ✅ Histórico leído ({n_registros} muestras). Lags calculados dinámicamente.")
    except Exception as e:
        print(f"   -> ⚠️ Error en lectura de lags: {e}. Usando nivel actual como contingencia.")
else:
    print("   -> ℹ️ Inicializando primer ciclo basal. Todos los lags igualados a t0.")

mes_actual = fecha_actual.month
sen_mes = float(np.sin(2 * np.pi * mes_actual / 12))
cos_mes = float(np.cos(2 * np.pi * mes_actual / 12))

# =========================================================================
# RECONSTRUCCIÓN DEL VECTOR DE CARACTERÍSTICAS Y ESCALADO SEGURO
# =========================================================================
print("\n🛠️  [4/6 - PREPROCESAMIENTO] Transformando vector mediante StandardScaler...")

vector_raw = np.array([[
    tp_t0, t2m_t0, nivel_actual, p_acum_12h, p_acum_24h,
    lag_1h, lag_4h, lag_8h, lag_12h, lag_24h,
    mes_actual, sen_mes, cos_mes
]])

vector_scaled = scaler.transform(vector_raw)
print("   -> 📏 Vector de 13 características escalado con alineación matemática perfecta.")

# =========================================================================
# EJECUCIÓN DEL BUCLE MAESTRO DE INFERENCIA MULTI-HORIZONTE
# =========================================================================
print("\n🧠 [5/6 - INFERENCIA] Evaluando el vector sobre las instancias residentes...")
registro_prediccion = {
    "fecha_ejecucion": fecha_str,
    "nivel_sensor_t0": nivel_actual
}

for h in horizontes_abreviados:
    print(f"   🚀 Procesando horizonte: {h} vista...")
    
    # --- JUEZ 1: INFERENCIA XGBOOST ---
    model_xgb = dict_modelos_xgb[h]
    if model_xgb is not None:
        pred_xgb = float(model_xgb.predict(vector_scaled)[0])
        print(f"      🌲 [Juez XGBoost]: {pred_xgb:.4f} m")
    else:
        pred_xgb = nivel_actual
        
    # --- JUEZ 2: INFERENCIA BiLSTM ---
    model_bilstm = dict_modelos_bilstm[h]
    if model_bilstm is not None:
        vector_3d = np.reshape(vector_scaled, (vector_scaled.shape[0], 1, vector_scaled.shape[1]))
        pred_bilstm = float(model_bilstm.predict(vector_3d, verbose=0).flatten()[0])
        print(f"      🧠 [Juez BiLSTM]:  {pred_bilstm:.4f} m")
    else:
        pred_bilstm = nivel_actual
        
    registro_prediccion[f"pred_xgb_{h}"] = pred_xgb
    registro_prediccion[f"pred_bilstm_{h}"] = pred_bilstm
    registro_prediccion[f"pred_tribunal_{h}"] = (0.50 * pred_xgb) + (0.50 * pred_bilstm)

# =========================================================================
# PERSISTENCIA EN EL HISTÓRICO DE PRODUCCIÓN
# =========================================================================
print("\n💾 [6/6 - PERSISTENCIA] Guardando resultados en el Data Lake local...")
df_nueva_fila = pd.DataFrame([registro_prediccion])

if os.path.exists(ruta_destino_predicciones):
    df_acumulado = pd.read_csv(ruta_destino_predicciones)
    df_final_log = pd.concat([df_acumulado, df_nueva_fila], ignore_index=True)
else:
    df_final_log = df_nueva_fila

df_final_log.to_csv(ruta_destino_predicciones, index=False)

print("\n" + "="*70)
print("🏆 INFORME DE INFERENCIA EN PRODUCCIÓN COMPLETADO (Framework Integrado)")
print("="*70)
for h in horizontes_abreviados:
    val = registro_prediccion[f"pred_tribunal_{h}"]
    print(f"  📈 Horizonte futuro [{h} horas vista] --> Predicción unificada: {val:.4f} metros")
print(f"\n💾 Registro histórico actualizado para análisis visual en: {ruta_destino_predicciones}")
print("=====================================================================\n")