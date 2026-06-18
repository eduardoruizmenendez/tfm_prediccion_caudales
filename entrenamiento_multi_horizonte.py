import os
import argparse
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from xgboost import XGBRegressor
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, Dense, LSTM, Bidirectional, Dropout
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras.optimizers import Adam

# Configuración de argumentos para la terminal
parser = argparse.ArgumentParser(description="Tribunal Cloud Multi-Horizonte (MIA - UNIR)")
parser.add_argument("--cuenca", type=str, required=True, help="id de la cuenca (urumea o besaya)")
args = parser.parse_args()
id_cuenca = args.cuenca.lower()

print("=====================================================================")
print(f"⚖️  PIPELINE MULTI-HORIZONTE: TRIBUNAL CLOUD (XGBOOST + BiLSTM)")
print(f"🦅 Cuenca de Análisis: Río {id_cuenca.upper()}")
print("=====================================================================\n")

# 1. CONTROL DE RUTAS Y DIRECTORIOS
ruta_dataset = f"data/output/dataset_entrenamiento/{id_cuenca}/matriz_entrenamiento_REAL_ESTACION.csv"
carpeta_modelos = f"data/output/modelos/{id_cuenca}"
carpeta_metricas = f"data/output/metricas/{id_cuenca}"
os.makedirs(carpeta_modelos, exist_ok=True)
os.makedirs(carpeta_metricas, exist_ok=True)

if not os.path.exists(ruta_dataset):
    print(f"❌ Error Crítico: No se encuentra la matriz en {ruta_dataset}")
    print("Por favor, ejecuta primero el generador de datasets.")
    exit()

# 2. CARGA Y LIMPIEZA DE DATOS ESTRUCTURALES
df_raw = pd.read_csv(ruta_dataset)
df_raw['fecha_hora'] = pd.to_datetime(df_raw['fecha_hora'])

# Purgamos las primeras filas que contienen NaN provocados por los lags hidrológicos
df = df_raw.dropna(subset=[c for c in df_raw.columns if 'TARGET' not in c and c != 'caudal_m3s']).reset_index(drop=True)

# Definimos los horizontes temporales exigidos por el TFM
horizontes_targets = ['TARGET_t+1', 'TARGET_t+4', 'TARGET_t+8', 'TARGET_t+12', 'TARGET_t+24']

# Identificamos y purgamos de las variables predictoras todo lo que huela a futuro o targets
columnas_excluir = horizontes_targets + [c for c in df.columns if 'fc_tp' in c] + ['fecha_hora', 'caudal_m3s']
features = [c for c in df.columns if c not in columnas_excluir]

print(f"📊 Variables predictoras limpias ({len(features)}): {features}")
print(f"🎯 Horizontes del Sistema de Alerta Temprana: {horizontes_targets}\n")

# Extraemos la matriz de entrada común X
X = df[features].values

# 3. DIVISIÓN CRONOLÓGICA TRIPLE (70% Train, 15% Val, 15% Test)
idx_val = int(len(df) * 0.7)
idx_test = int(len(df) * 0.85)

X_train_raw = X[:idx_val]
X_val_raw = X[idx_val:idx_test]
X_test_raw = X[idx_test:]

# Escalado estricto sin contaminación temporal (Data Leakage)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_raw)
X_val_scaled = scaler.transform(X_val_raw)
X_test_scaled = scaler.transform(X_test_raw)

# Congelamos el escalador en el disco duro antes del bucle
ruta_save_scaler = os.path.join(carpeta_modelos, f"scaler_{id_cuenca}.pkl")
joblib.dump(scaler, ruta_save_scaler)
print(f"📊 [DATA PIPELINE] Escalador unificado guardado en: {ruta_save_scaler}\n")

# Diccionario maestro para almacenar las métricas de todos los horizontes
historico_metricas = []

# =========================================================================
# 4. BUCLE MAESTRO MULTI-HORIZONTE
# =========================================================================
for target_actual in horizontes_targets:
    print("\n" + "="*70)
    print(f"🚀 INICIANDO ENTRENAMIENTO PARA EL OBJETIVO: {target_actual}")
    print("="*70 + "\n")
    
    # Extraemos el vector target correspondiente a este horizonte
    y = df[target_actual].values
    y_train = y[:idx_val]
    y_val = y[idx_val:idx_test]
    y_test = y[idx_test:]
    
    # -------------------------------------------------------------------------
    # JUEZ 1: Entrenando XGBoost Regressor (CON EARLY STOPPING ACTIVADO 🛠️)
    # -------------------------------------------------------------------------
    print(f"🌲 [1/2] Entrenando XGBoost Regressor para {target_actual}...")
    modelo_xgb = XGBRegressor(
        n_estimators=150, 
        learning_rate=0.05, 
        max_depth=6, 
        early_stopping_rounds=15,  # <-- 🛠️ ¡Aquí está la paciencia fijada!
        random_state=42
    )
    # Le pasamos el conjunto de validación para monitorizar la parada anticipada
    modelo_xgb.fit(
        X_train_scaled, y_train, 
        eval_set=[(X_val_scaled, y_val)], 
        verbose=False
    )
    
    # Predicción de XGBoost en Test (usa automáticamente el mejor árbol guardado)
    pred_xgb = modelo_xgb.predict(X_test_scaled)
    
    # Guardamos el archivo pkl de XGBoost
    ruta_save_xgb = os.path.join(carpeta_modelos, f"xgboost_{target_actual}.pkl")
    joblib.dump(modelo_xgb, ruta_save_xgb)
    print(f"   -> ✅ Guardado y optimizado con Early Stop: {ruta_save_xgb}")
    
    # -------------------------------------------------------------------------
    # JUEZ 2: Entrenando BiLSTM Sincronizada 2D
    # -------------------------------------------------------------------------
    print(f"🧠 [2/2] Configurando y entrenando BiLSTM para {target_actual}...")
    
    # Formateo tridimensional ágil para sincronización estricta 1:1
    X_train_3d = np.reshape(X_train_scaled, (X_train_scaled.shape[0], 1, X_train_scaled.shape[1]))
    X_val_3d = np.reshape(X_val_scaled, (X_val_scaled.shape[0], 1, X_val_scaled.shape[1]))
    X_test_3d = np.reshape(X_test_scaled, (X_test_scaled.shape[0], 1, X_test_scaled.shape[1]))
    
    # Definición de la arquitectura libre de bloqueos ReLU
    modelo_bilstm = Sequential([
        Input(shape=(1, X_train_scaled.shape[1])),
        Bidirectional(LSTM(32)),
        Dropout(0.2),
        Dense(16, activation='tanh'),
        Dense(1, activation='linear')
    ])
    
    modelo_bilstm.compile(optimizer=Adam(learning_rate=0.005), loss='mse')
    
    ruta_save_bilstm = os.path.join(carpeta_modelos, f"bilstm_{target_actual}.keras")
    
    callbacks_lista = [
        EarlyStopping(monitor='val_loss', patience=8, restore_best_weights=True, verbose=0),
        ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, min_lr=1e-6, verbose=0),
        ModelCheckpoint(filepath=ruta_save_bilstm, monitor='val_loss', save_best_only=True, verbose=0)
    ]
    
    modelo_bilstm.fit(
        X_train_3d, y_train,
        epochs=40,
        batch_size=32,
        validation_data=(X_val_3d, y_val),
        callbacks=callbacks_lista,
        verbose=1
    )
    
    # Predicción de la BiLSTM en Test (cargando los mejores pesos guardados)
    if os.path.exists(ruta_save_bilstm):
        modelo_bilstm = tf.keras.models.load_model(ruta_save_bilstm)
    pred_bilstm = modelo_bilstm.predict(X_test_3d, verbose=0).flatten()
    print(f"   -> ✅ Guardado: {ruta_save_bilstm}")
    
    # -------------------------------------------------------------------------
    # VEREDICTO FINAL DEL TRIBUNAL (Ensemble 50/50)
    # -------------------------------------------------------------------------
    pred_tribunal = (0.50 * pred_xgb) + (0.50 * pred_bilstm)
    
    # -------------------------------------------------------------------------
    # CÁLCULO EVALUACIÓN ESTADÍSTICA DEL HORIZONTE
    # -------------------------------------------------------------------------
    modelos_bucle = {
        "XGBoost": pred_xgb,
        "BiLSTM": pred_bilstm,
        "Tribunal": pred_tribunal
    }
    
    for nombre_mod, prediccion in modelos_bucle.items():
        rmse = np.sqrt(mean_squared_error(y_test, prediccion))
        mae = mean_absolute_error(y_test, prediccion)
        r2 = r2_score(y_test, prediccion)
        
        historico_metricas.append({
            "Horizonte": target_actual.replace("TARGET_", ""),
            "Modelo": nombre_mod,
            "R2": r2,
            "RMSE": rmse,
            "MAE": mae
        })

# =========================================================================
# 5. CONSOLIDACIÓN DE RESULTADOS FINALES Y EXPORTACIÓN MACRO
# =========================================================================
print("\n" + "="*70)
print("🏆 INFORME MACRO DE RENDIMIENTO MULTI-HORIZONTE")
print("="*70)

df_global_metricas = pd.DataFrame(historico_metricas)

# Ordenamiento categórico estricto para evitar ordenación alfabética desordenada
orden_cronologico = ['t+1', 't+4', 't+8', 't+12', 't+24']
df_global_metricas['Horizonte'] = pd.Categorical(df_global_metricas['Horizonte'], categories=orden_cronologico, ordered=True)
df_global_metricas = df_global_metricas.sort_values(by=['Horizonte', 'Modelo']).reset_index(drop=True)

# Visualización limpia indexada por horizonte para el documento Word
df_print = df_global_metricas.set_index(['Horizonte', 'Modelo'])
print(df_print.to_string())

# Guardamos el reporte consolidado en el Data Lake
ruta_reporte_final = os.path.join(carpeta_metricas, "reporte_consolidado_multihorizonte.csv")
df_global_metricas.to_csv(ruta_reporte_final, index=False)
print(f"\n💾 Archivo macro de métricas guardado en: {ruta_reporte_final}")
print("=====================================================================\n")