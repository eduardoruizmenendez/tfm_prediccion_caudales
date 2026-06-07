import requests
import pandas as pd
from datetime import datetime
from utils_adquisicion_datos import hacer_peticion_robusta, obtener_argumentos_y_config

# =====================================================================
# FUNCIÓN DE EXTRACCIÓN Y PARSEO (TIEMPO REAL)
# =====================================================================
def descargar_aemet_horario(api_key, id_estacion, prefijo):
    print(f"📡 Conectando con AEMET (Tiempo Real) para la estación {id_estacion}...")
    
    url_peticion = f"https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/{id_estacion}"
    querystring = {"api_key": api_key}
    headers = {'cache-control': "no-cache"}
    
    # PASO 1: Petición robusta para obtener la URL temporal
    res_1 = hacer_peticion_robusta(url_peticion, headers=headers, params=querystring)
    
    if res_1 is None: 
        return None
        
    datos_res_1 = res_1.json()
    
    # --- GESTIÓN DE CONTROL DE ESTADO ---
    if datos_res_1.get('estado') == 200:
        url_datos = datos_res_1.get('datos')
        print("✅ Permiso concedido. Descargando datos horarios consolidados...")
        
        # PASO 2: Descarga del JSON de observación real
        res_2 = hacer_peticion_robusta(url_datos)
        if res_2 is None: 
            return None
            
        datos_reales = res_2.json()
        df = pd.DataFrame(datos_reales)
        
        # PASO 3: Limpieza y formato de la serie temporal reciente
        if 'fint' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fint'])
            
            # Filtramos solo las variables analíticas necesarias para el vector Xt
            columnas_deseadas = ['fecha_hora']
            if 'prec' in df.columns: columnas_deseadas.append('prec')
            if 'ta' in df.columns: columnas_deseadas.append('ta')
            
            df_limpio = df[columnas_deseadas].copy()
            df_limpio = df_limpio.sort_values('fecha_hora').reset_index(drop=True)
            
            # Rellenar vacíos horarios (si no llueve, AEMET a veces omite el registro o manda NaN)
            if 'prec' in df_limpio.columns:
                df_limpio['prec'] = df_limpio['prec'].fillna(0.0)
            
            # Guardamos el archivo usando el prefijo dinámico
            nombre_csv = f"{prefijo}_aemet_actual.csv"
            df_limpio.to_csv(nombre_csv, index=False)
            print(f"💾 ¡Éxito! Datos de observación guardados en {nombre_csv}")
            
            return df_limpio
        else:
            print("⚠️ No se encontró la columna de tiempo (fint) en los datos devueltos por AEMET.")
            return df
            
    # --- MATRIZ DE CONTINGENCIA ACTIVA POR CAÍDA DE TELEMETRÍA ---
    elif datos_res_1.get('estado') == 404 or "No hay datos" in datos_res_1.get('descripcion', ''):
        print("   ⚠️ La estación de referencia está temporalmente desconectada de la red.")
        print("   -> Generando matriz de contingencia (Dummy Row) para no bloquear la inferencia.")
        
        # Replicamos la estructura exacta del vector con la hora actual redondeada
        hora_actual = pd.Timestamp.now().floor('h')
        df_emergencia = pd.DataFrame([{
            'fecha_hora': hora_actual,
            'prec': 0.0,  # Asumimos ausencia de precipitación por omisión (moda estadística)
            'ta': None    # Forzamos nulo matemático (NaN) gestionado por el split finding de XGBoost
        }])
        
        nombre_csv = f"{prefijo}_{id_estacion}_actual.csv"
        df_emergencia.to_csv(nombre_csv, index=False)
        print(f"💾 Fichero de contingencia guardado en {nombre_csv}")
        return df_emergencia
        
    else:
        print(f"❌ Error de la infraestructura de AEMET: {datos_res_1.get('descripcion')}")
        return None

# =====================================================================
# INTERFAZ POR LÍNEA DE COMANDOS (CLI)
# =====================================================================
if __name__ == "__main__":
    # Desestructuramos los tres valores que devuelve la utilidad unificada
    id_cuenca, parametros, credenciales = obtener_argumentos_y_config()
    
    ESTACION = parametros["aemet_estacion"]
    PREFIJO = parametros["prefijo_archivos_aemet"]
    
    print(f"🚀 INICIANDO EXTRACCIÓN EN TIEMPO REAL PARA: {parametros['nombre_legible']}")
    
    df_tiempo_real = descargar_aemet_horario(credenciales["AEMET"], ESTACION, PREFIJO)
    
    if df_tiempo_real is not None:
        print("\nÚltimos registros detectados en el pipeline:")
        print(df_tiempo_real.tail(3))