# entrenar_tribunal_cloud.py
import os
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Bidirectional, Dropout, BatchNormalization, Input
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras.optimizers import Adam
from utils_adquisicion_datos import obtener_argumentos_y_config
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

def preparar_datos_bilstm(X_scaled, window_size=24):
    """Transforma la matriz 2D en la estructura 3D que exige la BiLSTM."""
    X_3d = []
    for i in range(len(X_scaled) - window_size + 1):
        X_3d.append(X_scaled[i:i+window_size, :])
    return np.array(X_3d)

if __name__ == "__main__":
    # CARGA DE CONFIGURACIÓN
    id_cuenca, parametros, _ = obtener_argumentos_y_config()
    
    print(f"=====================================================================")
    print(f"⚖️  TRIBUNAL CLOUD (BiLSTM + XGBOOST)")
    print(f"🦅 Cuenca: {parametros['nombre_legible']}")
    print(f"=====================================================================\n")
    
    # CARGA DEL DATASET Y PURGA DE FEATURES FUTURAS (COMPLETO Y LIMPIO)
    ruta_dataset = f"data/output/dataset_entrenamiento/{id_cuenca}/matriz_entrenamiento_REAL_ESTACION.csv"
    
    if not os.path.exists(ruta_dataset):
        print(f"❌ Error: No se encuentra la matriz en {ruta_dataset}")
        exit()
        
    df = pd.read_csv(ruta_dataset)
    df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
    
    # Eliminamos las filas iniciales con NaNs debidos a los lags
    df = df.dropna(subset=[c for c in df.columns if 'TARGET' not in c and c != 'caudal_m3s'])
    
    # Excluimos todo lo que mire al futuro
    columnas_excluir = (
        [c for c in df.columns if 'TARGET' in c] + 
        [c for c in df.columns if 'fc_tp' in c] + 
        ['fecha_hora', 'caudal_m3s']
    )
    
    features = [c for c in df.columns if c not in columnas_excluir]
    target_seleccionado = 'TARGET_t+4'
    
    print(f"📊 Variables predictoras limpias para BiLSTM ({len(features)}): {features}")
    print(f"🎯 Variable objetivo del Tribunal: '{target_seleccionado}'\n")
    
    X = df[features].values
    y = df[target_seleccionado].values
    
    # DIVISIÓN CRONOLÓGICA
    # 70% Entrenamiento, 15% Validación (para callbacks), 15% Test final
    idx_val = int(len(df) * 0.7)
    idx_test = int(len(df) * 0.85)
    
    X_train_raw, y_train = X[:idx_val], y[:idx_val]
    X_val_raw, y_val = X[idx_val:idx_test], y[idx_val:idx_test]
    X_test_raw, y_test = X[idx_test:], y[idx_test:]
    
    # Escalado
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_val_scaled = scaler.transform(X_val_raw)
    X_test_scaled = scaler.transform(X_test_raw)
    
    # ENTRENAMIENTO MODELO 1: XGBOOST REGRESSOR
    print("🌲 Entrenando Model 1: XGBoost Regressor...")
    modelo_xgb = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    modelo_xgb.fit(X_train_scaled, y_train)
    pred_xgb = modelo_xgb.predict(X_test_scaled)
    print("   -> ✅ XGBoost entrenado con éxito.")
    
    # 5. ENTRENAMIENTO MODELO 2: BiLSTM
    print("\n🧠 Configurando y entrenando Model 2: BiLSTM Sincronizada...")
    
    # Rediseño estructural: Redefinimos la entrada como (1 paso de tiempo, N características)
    # De esta manera, cada fila se procesa de forma independiente y no se pierde ni una sola fila
    X_train_3d = np.reshape(X_train_scaled, (X_train_scaled.shape[0], 1, X_train_scaled.shape[1]))
    X_val_3d = np.reshape(X_val_scaled, (X_val_scaled.shape[0], 1, X_val_scaled.shape[1]))
    X_test_3d = np.reshape(X_test_scaled, (X_test_scaled.shape[0], 1, X_test_scaled.shape[1]))
    
    modelo_bilstm = Sequential([
        Input(shape=(1, X_train_scaled.shape[1])),
        Bidirectional(LSTM(32)),
        Dropout(0.2),
        Dense(16, activation='tanh'),
        Dense(1, activation='linear')
    ])
    
    modelo_bilstm.compile(optimizer=Adam(learning_rate=0.005), loss='mse')
    
    callbacks_lista = [
        EarlyStopping(monitor='val_loss', patience=8, restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, min_lr=1e-6, verbose=1),
        ModelCheckpoint(filepath=f"data/output/dataset_entrenamiento/{id_cuenca}/mejor_bilstm.keras", monitor='val_loss', save_best_only=True, verbose=1)
    ]
    
    modelo_bilstm.fit(
        X_train_3d, y_train,
        epochs=40,
        batch_size=32,
        validation_data=(X_val_3d, y_val),
        callbacks=callbacks_lista,
        verbose=1
    )
    
    pred_bilstm = modelo_bilstm.predict(X_test_3d).flatten()
    print("   -> ✅ BiLSTM entrenada y perfectamente alineada.")
    
    # CONSTITUCIÓN DEL TRIBUNAL
    print("\n⚖️  Constituyendo el veredicto del Tribunal...")
    
    pred_tribunal = (0.50 * pred_xgb) + (0.50 * pred_bilstm)
    
    df_resultados = pd.DataFrame({
        "Nivel_Real_m": y_test,
        "Prediccion_XGB": pred_xgb,
        "Prediccion_BiLSTM": pred_bilstm,
        "Prediccion_Tribunal": pred_tribunal
    })
    
    # VISUALIZACIÓN DEL MOMENTO DE MÁXIMA VARIACIÓN
    variabilidad = df_resultados['Nivel_Real_m'].rolling(window=10).std()
    idx_max_var = variabilidad.idxmax()
    
    print(f"\n🔬 Muestra del Tribunal en el momento de MÁXIMA VARIACIÓN:")
    if pd.notna(idx_max_var):
        print(df_resultados.iloc[max(0, idx_max_var-5):min(len(df_resultados), idx_max_var+5)].to_string())
    else:
        print(df_resultados.head(10).to_string())
        
    print("\n=====================================================================")
    
    # CÁLCULO DE MÉTRICAS ESTADÍSTICAS OFICIALES
    print("\n📊 Calculando métricas de rendimiento en el conjunto de Test...")
    
    # Diccionario para empaquetar los resultados
    metodo_metricas = {}
    
    modelos_evaluar = {
        "XGBoost": pred_xgb,
        "BiLSTM": pred_bilstm,
        "Tribunal (Ensemble)": pred_tribunal
    }
    
    for nombre, prediccion in modelos_evaluar.items():
        rmse = np.sqrt(mean_squared_error(y_test, prediccion))
        mae = mean_absolute_error(y_test, prediccion)
        r2 = r2_score(y_test, prediccion)
        
        metodo_metricas[nombre] = {"RMSE": rmse, "MAE": mae, "R2": r2}
    
    # Convertimos a DataFrame
    df_metricas = pd.DataFrame(metodo_metricas).T
    print("\n🏆 TABLA COMPARATIVA DE RENDIMIENTO (HORIZONTE t+4):")
    print(df_metricas.to_string())
    
    # 💾 GUARDADO EN EL DATA LAKE
    ruta_metricas = f"data/output/dataset_entrenamiento/{id_cuenca}/metricas_tribunal_t4.csv"
    df_metricas.to_csv(ruta_metricas, index=True)
    print(f"\n💾 Informe de métricas exportado correctamente a: {ruta_metricas}")
    print("\n=====================================================================")