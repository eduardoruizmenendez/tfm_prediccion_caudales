# generador_dataset_entrenamiento_2.py
import os
import glob
import pandas as pd
import numpy as np
from utils_adquisicion_datos import obtener_argumentos_y_config

if __name__ == "__main__":
    # 1. CARGA DE CONFIGURACIÓN Y PARSER CLI
    id_cuenca, parametros, _ = obtener_argumentos_y_config()
    
    print(f"=====================================================================")
    print(f"🚀 INICIANDO CONSTRUCCIÓN DE DATASET MAESTRO PARA XGBOOST")
    print(f"🦅 Cuenca: {parametros['nombre_legible']}")
    print(f"=====================================================================\n")
    
    # 2. CONFIGURACIÓN DE RUTAS Y PREFIJOS
    ruta_lluvia = parametros["carpeta_lluvia_h"]
    prefijo_lluvia = parametros["prefijo_fichero_lluvia_h"]
    
    ruta_caudal_glofas = parametros["carpeta_caudal_h"]
    prefijo_caudal = parametros["prefijo_fichero_caudal_h"]
    
    ruta_hidro_real = parametros.get("carpeta_hidro_h", ruta_caudal_glofas)

    def ensamblar_archivos_mensuales(ruta_carpeta, prefijo_archivo):
        patron = os.path.join(ruta_carpeta, f"{prefijo_archivo}_*.csv")
        archivos = glob.glob(patron)
        if not archivos:
            return pd.DataFrame()
        print(f"   -> [Glob] Encontrados {len(archivos)} archivos mensuales para '{prefijo_archivo}'.")
        return pd.concat([pd.read_csv(f) for f in archivos], ignore_index=True)

    # 3. CARGA DINÁMICA DE REPOSITORIOS
    print(f"📖 Ensamblando histórico climático mensual (ERA5-Land)...")
    df_lluvia_raw = ensamblar_archivos_mensuales(ruta_lluvia, prefijo_lluvia)
    
    # Comprobamos si el descargador estático real dejó su archivo maestro unificado
    fichero_hidro_real = os.path.join(ruta_hidro_real, f"{prefijo_caudal}_real_completo.csv")
    
    if os.path.exists(fichero_hidro_real):
        print(f"📡 🟩 [DETECTADO] Cargando histórico HORARIO REAL de estación: {fichero_hidro_real}")
        df_caudal_raw = pd.read_csv(fichero_hidro_real)
        es_datos_diarios_glofas = False
    else:
        print(f"🌍 🟧 [FALLBACK] No se detectó histórico real. Ensamblando simulación GloFAS...")
        df_caudal_raw = ensamblar_archivos_mensuales(ruta_caudal_glofas, prefijo_caudal)
        es_datos_diarios_glofas = True

    if df_lluvia_raw.empty or df_caudal_raw.empty:
        print("❌ Error Crítico: No se encontraron archivos para procesar. Revisa las rutas de entrada.")
        exit()

    # =========================================================================
    # 4. NORMALIZACIÓN CRÍTICA DE COLUMNAS DE TIEMPO
    # =========================================================================
    print("🧹 Normalizando cabeceras temporales de forma dinámica...")
    variantes_tiempo = ['fecha_hora', 'valid_time', 'time', 'fecha', 'timestamp']
    
    col_t_lluvia = next((c for c in variantes_tiempo if c in df_lluvia_raw.columns), None)
    if col_t_lluvia:
        fechas_convertidas = pd.to_datetime(df_lluvia_raw[col_t_lluvia])
        if fechas_convertidas.dt.tz is not None:
            df_lluvia_raw['fecha_hora_std'] = fechas_convertidas.dt.tz_localize(None)
        else:
            df_lluvia_raw['fecha_hora_std'] = fechas_convertidas
    else:
        print("❌ Error: No hay columna de tiempo en clima.")
        exit()
        
    col_t_caudal = next((c for c in variantes_tiempo if c in df_caudal_raw.columns), None)
    if col_t_caudal:
        df_caudal_raw['fecha_hora_std'] = pd.to_datetime(df_caudal_raw[col_t_caudal])
    else:
        print("❌ Error: No hay columna de tiempo en hidrología.")
        exit()

    # =========================================================================
    # 5. APLANAMIENTO ASIMÉTRICO Y SELECCIÓN SIMÉTRICA DE TARGETS
    # =========================================================================
    print("⚖️ Ejecutando ordenación areal y verificación de variables objetivo...")
    
    col_tp = 'tp' if 'tp' in df_lluvia_raw.columns else 'precipitation'
    col_t2m = 't2m' if 't2m' in df_lluvia_raw.columns else '2m_temperature'
    
    df_lluvia = df_lluvia_raw.groupby('fecha_hora_std')[[col_tp, col_t2m]].mean().reset_index()

    # Mantenemos las dos columnas estructurales para conservar simetría multifluvio
    columnas_hidro_interes = []
    if 'nivel_m' in df_caudal_raw.columns:
        columnas_hidro_interes.append('nivel_m')
    if 'caudal_m3s' in df_caudal_raw.columns:
        columnas_hidro_interes.append('caudal_m3s')
    if 'dis24' in df_caudal_raw.columns:
        columnas_hidro_interes.append('dis24')

    if not es_datos_diarios_glofas:
        print(f"   -> 🌊 Extrayendo matriz real unificada: {columnas_hidro_interes}")
        df_caudal = df_caudal_raw.groupby('fecha_hora_std')[columnas_hidro_interes].first().reset_index()
    else:
        # Lógica de extracción de píxel máximo para simulaciones de GloFAS
        lat_max = df_caudal_raw['latitude'].max()
        lon_correspondiente = df_caudal_raw[df_caudal_raw['latitude'] == lat_max]['longitude'].iloc[0]
        df_caudal_punto = df_caudal_raw[(df_caudal_raw['latitude'] == lat_max) & (df_caudal_raw['longitude'] == lon_correspondiente)].copy()
        df_caudal = df_caudal_punto.groupby('fecha_hora_std')[columnas_hidro_interes].first().reset_index()

    # 6. CRUCE TEMPORAL UNIFICADO (MERGE 1:1)
    print(f"🔀 Unificando series mediante Left Join Horario...")
    
    df_lluvia['fecha_hora_std'] = pd.to_datetime(df_lluvia['fecha_hora_std']).dt.tz_localize(None)
    df_caudal['fecha_hora_std'] = pd.to_datetime(df_caudal['fecha_hora_std']).dt.tz_localize(None)
    
    df_lluvia = df_lluvia.sort_values('fecha_hora_std').reset_index(drop=True)
    df_caudal = df_caudal.sort_values('fecha_hora_std').reset_index(drop=True)
    
    df = pd.merge(df_lluvia, df_caudal, on='fecha_hora_std', how='left')
    df = df.sort_values('fecha_hora_std').reset_index(drop=True)
    
    # Normalización formal de nombres
    df.rename(columns={'fecha_hora_std': 'fecha_hora', col_tp: 'tp', col_t2m: 't2m'}, inplace=True)
    if 'dis24' in df.columns:
        df.rename(columns={'dis24': 'caudal_m3s'}, inplace=True)

    # Definimos dinámicamente cuál es nuestra variable predictiva real de control (Target base)
    # Si tenemos el nivel del río real, el XGBoost se enfocará en predecir 'nivel_m'
    col_target_base = 'nivel_m' if 'nivel_m' in df.columns and df['nivel_m'].notna().sum() > 0 else 'caudal_m3s'
    print(f"   🎯 Variable base seleccionada para ventanas predictivas: '{col_target_base}'")

    # Tratamiento controlado de nulos en la señal base
    if es_datos_diarios_glofas:
        print("   -> 🩹 Rellenando saltos diarios de GloFAS a escala horaria (Forward Fill)...")
        df[col_target_base] = df[col_target_base].ffill()
    else:
        df[col_target_base] = df[col_target_base].interpolate(method='linear', limit=3)
        
    df = df.dropna(subset=[col_target_base]).reset_index(drop=True)
    
    # 7. MOTOR DE CARACTERÍSTICAS (FEATURE ENGINEERING)
    print(f"🛠️ Aplicando motor de Features e Ingeniería de Lags...")
    
    if df['tp'].max() < 0.1:
        df['tp'] = df['tp'] * 1000.0  # m -> mm
    if df['t2m'].max() > 150:
        df['t2m'] = df['t2m'] - 273.15  # K -> °C
        
    df['p_acum_12h'] = df['tp'].rolling(window=12, min_periods=1).sum()
    df['p_acum_24h'] = df['tp'].rolling(window=24, min_periods=1).sum()
    
    df['fc_tp_1h'] = df['tp'].shift(-1)
    df['fc_tp_4h'] = df['tp'].iloc[::-1].rolling(window=4, min_periods=1).sum().iloc[::-1].shift(-4)
    df['fc_tp_8h'] = df['tp'].iloc[::-1].rolling(window=8, min_periods=1).sum().iloc[::-1].shift(-8)
    df['fc_tp_12h'] = df['tp'].iloc[::-1].rolling(window=12, min_periods=1).sum().iloc[::-1].shift(-12)
    df['fc_tp_24h'] = df['tp'].iloc[::-1].rolling(window=24, min_periods=1).sum().iloc[::-1].shift(-24)
    
    # Generación adaptativa de características históricas pasadas (Lags)
    df['hidro_t-1'] = df[col_target_base].shift(1)
    df['hidro_t-4'] = df[col_target_base].shift(4)
    df['hidro_t-8'] = df[col_target_base].shift(8)
    df['hidro_t-12'] = df[col_target_base].shift(12)
    df['hidro_t-24'] = df[col_target_base].shift(24)
    
    df['mes'] = df['fecha_hora'].dt.month
    df['sen_mes'] = np.sin(2 * np.pi * df['mes'] / 12)
    df['cos_mes'] = np.cos(2 * np.pi * df['mes'] / 12)
    
    # Generación adaptativa de objetivos de futuro (Horizontes de predicción del TFM)
    df['TARGET_t+1'] = df[col_target_base].shift(-1)
    df['TARGET_t+4'] = df[col_target_base].shift(-4)
    df['TARGET_t+8'] = df[col_target_base].shift(-8)
    df['TARGET_t+12'] = df[col_target_base].shift(-12)
    df['TARGET_t+24'] = df[col_target_base].shift(-24)
    
    # Limpieza final: eliminamos las filas extremas que se quedan sin ventanas por los shifts
    df_final = df.dropna(subset=['TARGET_t+1', 'TARGET_t+4', 'TARGET_t+8', 'TARGET_t+12', 'TARGET_t+24']).reset_index(drop=True)
    
    # 8. GUARDADO MAESTRO AUTOMATIZADO
    carpeta_salida = f"data/output/dataset_entrenamiento/{id_cuenca}/"
    os.makedirs(carpeta_salida, exist_ok=True)
    
    origen_str = "REAL_ESTACION" if not es_datos_diarios_glofas else "SIMULADO_GLOFAS"
    nombre_master = os.path.join(carpeta_salida, f"matriz_entrenamiento_{origen_str}.csv")
    df_final.to_csv(nombre_master, index=False)
    
    print(f"\n🏆 ¡DATASET CONSTRUIDO CON ÉXITO!")
    print(f"💾 Guardado en: {nombre_master}")
    print(f"📊 Dataset final: {df_final.shape[0]} filas × {df_final.shape[1]} columnas.")
    print(f"=====================================================================\n")