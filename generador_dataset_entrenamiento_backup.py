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

    # Función para concatenar meses sueltos de Copernicus
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
    # 4. NORMALIZACIÓN CRÍTICA DE COLUMNAS DE TIEMPO (BLINDAJE ANTI-KEYERROR)
    # =========================================================================
    print("🧹 Normalizando cabeceras temporales de forma dinámica...")
    variantes_tiempo = ['fecha_hora', 'valid_time', 'time', 'fecha', 'timestamp']
    
    # Normalizar Clima
    col_t_lluvia = next((c for c in variantes_tiempo if c in df_lluvia_raw.columns), None)
    if col_t_lluvia:
        df_lluvia_raw['fecha_hora_std'] = pd.to_datetime(df_lluvia_raw[col_t_lluvia])
    else:
        print(f"❌ Error: No hay columna de tiempo en clima. Columnas: {list(df_lluvia_raw.columns)}")
        exit()
        
    # Normalizar Hidrología
    col_t_caudal = next((c for c in variantes_tiempo if c in df_caudal_raw.columns), None)
    if col_t_caudal:
        df_caudal_raw['fecha_hora_std'] = pd.to_datetime(df_caudal_raw[col_t_caudal])
    else:
        print(f"❌ Error: No hay columna de tiempo en hidrología. Columnas: {list(df_caudal_raw.columns)}")
        exit()

    # =========================================================================
    # 5. APLANAMIENTO ASIMÉTRICO (CONTROL DE CALIDAD ESPACIAL)
    # =========================================================================
    print("分割 Ejecutando aplanamiento para evitar duplicación de coordenadas...")
    
    col_tp = 'tp' if 'tp' in df_lluvia_raw.columns else 'precipitation'
    col_t2m = 't2m' if 't2m' in df_lluvia_raw.columns else '2m_temperature'
    
    # LLUVIA: Promedio Areal usando nuestra columna estandarizada segura
    df_lluvia = df_lluvia_raw.groupby('fecha_hora_std')[[col_tp, col_t2m]].mean().reset_index()

    # HIDROLOGÍA: Selección de la variable objetivo (Nivel vs Caudal)
    if 'nivel_m' in df_caudal_raw.columns and df_caudal_raw['nivel_m'].notna().sum() > 0:
        col_dis = 'nivel_m'
        print("   -> 🌊 Decisión Analítica: Seleccionado 'nivel_m' (Nivel real en metros) como Target.")
        df_caudal = df_caudal_raw.groupby('fecha_hora_std')[[col_dis]].first().reset_index()
    else:
        col_dis = 'caudal_m3s' if 'caudal_m3s' in df_caudal_raw.columns else 'dis24'
        print(f"   -> 💧 Decisión Analítica: Seleccionada variable '{col_dis}' como Target.")
        
        if es_datos_diarios_glofas:
            # Aislamiento del píxel de salida para GloFAS
            lat_max = df_caudal_raw['latitude'].max()
            lon_correspondiente = df_caudal_raw[df_caudal_raw['latitude'] == lat_max]['longitude'].iloc[0]
            df_caudal_punto = df_caudal_raw[(df_caudal_raw['latitude'] == lat_max) & (df_caudal_raw['longitude'] == lon_correspondiente)].copy()
            df_caudal = df_caudal_punto.groupby('fecha_hora_std')[[col_dis]].first().reset_index()
        else:
            df_caudal = df_caudal_raw.groupby('fecha_hora_std')[[col_dis]].first().reset_index()

    # 6. CRUCE TEMPORAL UNIFICADO (MERGE 1:1 SEGURO)
    print(f"🔀 Unificando series mediante Left Join Horario...")
    df_lluvia = df_lluvia.sort_values('fecha_hora_std').reset_index(drop=True)
    df_caudal = df_caudal.sort_values('fecha_hora_std').reset_index(drop=True)
    
    df = pd.merge(df_lluvia, df_caudal, on='fecha_hora_std', how='left')
    df = df.sort_values('fecha_hora_std').reset_index(drop=True)
    
    # Cambiamos las cabeceras finales al formato estándar del pipeline
    df.rename(columns={'fecha_hora_std': 'fecha_hora', col_tp: 'tp', col_t2m: 't2m', col_dis: 'caudal_m3s'}, inplace=True)
    
    # Tratamiento de valores nulos temporales
    if es_datos_diarios_glofas:
        print("   -> 🩹 Rellenando saltos diarios de GloFAS a escala horaria (Forward Fill)...")
        df['caudal_m3s'] = df['caudal_m3s'].ffill()
    else:
        df['caudal_m3s'] = df['caudal_m3s'].interpolate(method='linear', limit=3)
        
    df = df.dropna(subset=['caudal_m3s']).reset_index(drop=True)
    
    # 7. MOTOR DE CARACTERÍSTICAS (FEATURE ENGINEERING)
    print(f"🛠️ Aplicando motor de Features...")
    
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
    
    df['caudal_t-1'] = df['caudal_m3s'].shift(1)
    df['caudal_t-4'] = df['caudal_m3s'].shift(4)
    df['caudal_t-8'] = df['caudal_m3s'].shift(8)
    df['caudal_t-12'] = df['caudal_m3s'].shift(12)
    df['caudal_t-24'] = df['caudal_m3s'].shift(24)
    
    df['mes'] = df['fecha_hora'].dt.month
    df['sen_mes'] = np.sin(2 * np.pi * df['mes'] / 12)
    df['cos_mes'] = np.cos(2 * np.pi * df['mes'] / 12)
    
    df['TARGET_caudal_t+1'] = df['caudal_m3s'].shift(-1)
    df['TARGET_caudal_t+4'] = df['caudal_m3s'].shift(-4)
    df['TARGET_caudal_t+8'] = df['caudal_m3s'].shift(-8)
    df['TARGET_caudal_t+12'] = df['caudal_m3s'].shift(-12)
    df['TARGET_caudal_t+24'] = df['caudal_m3s'].shift(-24)
    
    df_final = df.dropna().reset_index(drop=True)
    
    # 8. GUARDADO MAESTRO AUTOMATIZADO
    carpeta_salida = f"data/output/dataset_entrenamiento/{id_cuenca}/"
    os.makedirs(carpeta_salida, exist_ok=True)
    
    origen_str = "REAL_ESTACION" if col_dis == 'nivel_m' else "SIMULADO_GLOFAS"
    nombre_master = os.path.join(carpeta_salida, f"matriz_entrenamiento_{origen_str}.csv")
    df_final.to_csv(nombre_master, index=False)
    
    print(f"\n🏆 ¡DATASET CONSTRUIDO CON ÉXITO!")
    print(f"💾 Guardado en: {nombre_master}")
    print(f"📊 Dataset final: {df_final.shape[0]} filas × {df_final.shape[1]} columnas.")
    print(f"=====================================================================\n")