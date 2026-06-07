import pandas as pd
import numpy as np
import xgboost as xgb
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_error, mean_squared_error

print("--- 📊 FASE 1: CARGA Y ANÁLISIS EXPLORATORIO ---")
df = pd.read_csv("master_train_besaya.csv")
df['valid_time'] = pd.to_datetime(df['valid_time'])
df = df.sort_values('valid_time').set_index('valid_time') # El índice ahora es la fecha

print(f"Total de registros: {len(df)}")
print("Buscando valores nulos...")
print(df.isnull().sum()[df.isnull().sum() > 0]) # Debería salir vacío si la limpieza fue bien

# Mapa de correlación rápido (solo algunas variables clave para no saturar)
cols_corr = ['caudal_m3s', 'tp', 'p_acum_24h', 'fc_tp_24h', 'TARGET_caudal_t+24']
plt.figure(figsize=(8, 6))
sns.heatmap(df[cols_corr].corr(), annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Matriz de Correlación: Variables Clave vs Objetivo 24h")
plt.show()

print("\n--- 🧠 FASE 2: PREPARACIÓN Y ENTRENAMIENTO ---")
# Separar variables predictoras (X) de los objetivos (y)
targets = ['TARGET_caudal_t+1', 'TARGET_caudal_t+4', 'TARGET_caudal_t+8', 'TARGET_caudal_t+12', 'TARGET_caudal_t+24']
X = df.drop(columns=targets)

# División Temporal Train/Test (80% pasado para entrenar, 20% futuro para validar)
corte = int(len(df) * 0.8)
X_train, X_test = X.iloc[:corte], X.iloc[corte:]

modelos_especialistas = {}
predicciones_test = {}

print("Entrenando la batería de modelos XGBoost...")
for target in targets:
    y = df[target]
    y_train, y_test = y.iloc[:corte], y.iloc[corte:]
    
    # Configuración del modelo (ajustado para series temporales)
    modelo = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=150,
        learning_rate=0.05,
        max_depth=5,
        random_state=42
    )
    
    # Entrenamiento silencioso
    modelo.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Guardamos el modelo entrenado y sus predicciones
    modelos_especialistas[target] = modelo
    predicciones_test[target] = modelo.predict(X_test)
    
    print(f"✅ Especialista para {target} entrenado con éxito.")

print("\n--- 📈 FASE 3: EVALUACIÓN Y RESULTADOS ---")
# Calculamos métricas para cada horizonte
for target in targets:
    y_real = df[target].iloc[corte:]
    y_pred = predicciones_test[target]
    
    mae = mean_absolute_error(y_real, y_pred)
    rmse = np.sqrt(mean_squared_error(y_real, y_pred))
    print(f"Horizonte {target[-3:]} -> MAE: {mae:.2f} m3/s | RMSE: {rmse:.2f} m3/s")

# Gráfica de la Prueba de Fuego: Realidad vs Predicción a 24 horas
target_plot = 'TARGET_caudal_t+24'
plt.figure(figsize=(15, 6))
plt.plot(X_test.index, df[target_plot].iloc[corte:], label='Caudal Real', color='blue', alpha=0.6)
plt.plot(X_test.index, predicciones_test[target_plot], label='Predicción XGBoost', color='red', alpha=0.8, linestyle='--')
plt.title(f'Validación en Test: Predicción a {target_plot[-3:]} vista')
plt.xlabel('Fecha')
plt.ylabel('Caudal (m3/s)')
plt.legend()
plt.grid(True)
plt.show()

# Importancia de las variables para el modelo a 24h
xgb.plot_importance(modelos_especialistas[target_plot], max_num_features=10, height=0.5, importance_type='weight')
plt.title(f"Importancia de Variables (Horizonte {target_plot[-3:]})")
plt.show()