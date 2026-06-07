import requests
import pandas as pd
from utils_adquisicion_datos import obtener_argumentos_y_config

# =====================================================================
# INTERFAZ POR LÍNEA DE COMANDOS (CLI) Y CARGA DE METADATOS
# =====================================================================
if __name__ == "__main__":
    
    # Desestructuramos el entorno global usando la función común
    id_cuenca, parametros, _ = obtener_argumentos_y_config()
    
    # Extraemos de forma dinámica los parámetros específicos de la configuración
    puntos = parametros["puntos_openmeteo"]
    archivo_csv = parametros["archivo_salida_openmeteo"]
    
    print(f"🚀 INICIANDO EXTRACCIÓN OPEN-METEO PARA: {parametros['nombre_legible']}")
    
    # Preparamos las coordenadas para la URL
    lats = ",".join([str(lat) for lat, lon in puntos.values()])
    lons = ",".join([str(lon) for lat, lon in puntos.values()])
    horizonte_horas = 72
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&hourly=precipitation&forecast_hours={horizonte_horas}"
    
    print("📡 Descargando previsiones multipunto en una sola ráfaga...")
    respuesta = requests.get(url)
    datos = respuesta.json()
    
    # --- TU BUCLE ORIGINAL DE CONSTRUCCIÓN Y MERGE ---
    for i, (nombre_nodo, coords) in enumerate(puntos.items()):
        df_temp = pd.DataFrame({
            "fecha_hora": pd.to_datetime(datos[i]["hourly"]["time"]),
            f"precip_mm_{nombre_nodo}": datos[i]["hourly"]["precipitation"]
        })
        
        if i == 0:
            df_forecast = df_temp
        else:
            df_forecast = pd.merge(df_forecast, df_temp, on="fecha_hora")
            
    # Cálculo de la Precipitación Media Areal
    columnas_precip = [col for col in df_forecast.columns if "precip_mm" in col]
    df_forecast["precipitacion_media_cuenca_mm"] = df_forecast[columnas_precip].mean(axis=1)
    
    print("\n✅ Cálculo areal completado con éxito.")
    print(df_forecast[["fecha_hora", "precipitacion_media_cuenca_mm"]].head(5))
    
    # Exportación automatizada de resultados según la cuenca activa
    df_forecast.to_csv(archivo_csv, index=False)
    print(f"\n💾 Archivo guardado correctamente en: {archivo_csv}\n")