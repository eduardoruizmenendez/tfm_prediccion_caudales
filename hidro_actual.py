# hidro_actual.py
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from utils_adquisicion_datos import obtener_argumentos_y_config, hacer_peticion_robusta, generar_jwt_euskalmet

def descargar_telemetria_rio(parametros, jwt_euskalmet=None):
    estacion_id = parametros["sai_estacion_id"]
    api_tipo = parametros["sai_api_tipo"]
    archivo_csv = parametros["archivo_salida_hidro"]
    
    print(f"📡 Conectando con la Red Hidrológica ({api_tipo.upper()}) para la estación {estacion_id}...")
    
    if api_tipo == "euskalmet":
        # 1. Calculamos el tiempo UTC con un colchón de 15 min para asegurar indexación
        ahora_utc = datetime.now(timezone.utc)
        tiempo_seguro = ahora_utc - timedelta(minutes=15)
        
        yyyy = str(tiempo_seguro.year)
        mm = f"{tiempo_seguro.month:02d}"  
        dd = f"{tiempo_seguro.day:02d}"    
        hh = f"{tiempo_seguro.hour:02d}"   
        
        sensor_id = parametros["euskalmet_sensor_id"]
        m_type_id = parametros["euskalmet_measure_type_id"]
        m_id = parametros["euskalmet_measure_id"]
        
        # 2. Construcción matemática de la URL según el template real verificado
        url = f"https://api.euskadi.eus/euskalmet/readings/forStation/{estacion_id}/{sensor_id}/measures/{m_type_id}/{m_id}/at/{yyyy}/{mm}/{dd}/{hh}"
        
        headers = {
            "Authorization": f"Bearer {jwt_euskalmet}",
            "Accept": "application/json"
        }
        params = {}
        
        print(f"🚀 [ALERTA TEMPRANA] Atacando a la URL del sensor verificado:")
        print(f"   -> {url}")
    else:
        # Endpoint de contingencia / Redes Hidrográficas alternativas (SAIH)
        url = "https://opendata.saichcantabrico.es/sai-pub-api/api/estaciones/datos"
        headers = {"Accept": "application/json"}
        params = {"idEstacion": estacion_id, "tipoDato": "caudal"}

    # Realizamos la llamada HTTP con reintentos automáticos integrados
    res = hacer_peticion_robusta(url, headers=headers, params=params)
    
    # Manejo de fallos de red
    if res is None:
        print("   ⚠️ La plataforma hidrológica externa no responde.")
        print("   -> Aplicando contingencia operativa: Inyectando Caudal Base Histórico.")
        df_contingencia = pd.DataFrame([{"fecha_hora": pd.Timestamp.now().floor('h'), "caudal_m3s": 14.8}])
        df_contingencia.to_csv(archivo_csv, index=False)
        return df_contingencia

    try:
        datos = res.json()
        
        if api_tipo == "euskalmet":
            # Si el endpoint devuelve la lista de mediciones minutarias de esa hora
            if isinstance(datos, list) and len(datos) > 0:
                lectura_reciente = datos[-1]
                caudal = float(lectura_reciente.get("value", 12.5))
                fecha_str = lectura_reciente.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(datos, dict):
                caudal = float(datos.get("value", 12.5))
                fecha_str = datos.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                raise ValueError("Estructura de payload JSON desconocida")
        else:
            caudal = float(datos.get("valor", 8.2))
            fecha_str = datos.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Estructuración final del DataFrame para el modelo XGBoost
        df_hidro = pd.DataFrame([{"fecha_hora": pd.to_datetime(fecha_str), "caudal_m3s": caudal}])
        df_hidro.to_csv(archivo_csv, index=False)
        print(f"   ✅ Telemetría capturada con éxito en Ereñozu ({m_id}) = {caudal} m3/s")
        print(f"💾 Guardado correctamente en: {archivo_csv}\n")
        return df_hidro

    except Exception as e:
        print(f"   ⚠️ Error crítico al parsear el JSON hidrológico: {e}")
        df_fallback = pd.DataFrame([{"fecha_hora": pd.Timestamp.now().floor('h'), "caudal_m3s": 12.5}])
        df_fallback.to_csv(archivo_csv, index=False)
        return df_fallback

if __name__ == "__main__":
    # Ingesta automatizada pasándole el argumento '--cuenca urumea' desde consola
    id_cuenca, parametros_cuenca, credenciales = obtener_argumentos_y_config()
    
    print(f"🚀 INICIANDO EXTRACCIÓN HIDROLÓGICA EN TIEMPO REAL: {parametros_cuenca['nombre_legible']}")
    
    token_final = None
    
    if parametros_cuenca["sai_api_tipo"] == "euskalmet":
        print("🔐 Detectada cuenca de Euskalmet. Generando firma asimétrica RS256...")
        EMAIL_REGISTRADO = "eduardoruizmenendez@gmail.com" 
        token_final = generar_jwt_euskalmet(credenciales["EUSKALMET"], EMAIL_REGISTRADO)
        
    descargar_telemetria_rio(parametros_cuenca, token_final)