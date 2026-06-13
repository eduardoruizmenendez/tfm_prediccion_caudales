# =====================================================================
# CONFIGURACIÓN CENTRALIZADA MULTI-API PARA EL PIPELINE HIDROLÓGICO
# =====================================================================

CONFIGURACION_CUENCAS = {
    "urumea": {
        "nombre_legible": "Río Urumea (País Vasco)",
        "prefijo_archivos": "urumea",
        
        # 1. Parámetros Copernicus (ERA5-Land y GloFAS)
        "coor_copernicus": [43.10, -2.05, 43.35, -1.75], 
        "puntos_openmeteo": {
            "Cabecera": (43.15, -1.91),
            "Tramo_Medio": (43.26, -1.97),
            "Desembocadura": (43.32, -1.98)
        },
        "archivo_salida_openmeteo": "openmeteo_urumea_forecast_areal.csv",
        "carpeta_caudal_h": "data/input/caudal_h/pais_vasco/",
        "prefijo_fichero_caudal_h": "caudal_historico",
        "carpeta_lluvia_h": "data/input/lluvia_h/pais_vasco/",
        "prefijo_fichero_lluvia_h": "lluvia_historica",
        
        # 2. Parámetros AEMET (Estación de Referencia e Inferencia)
        "aemet_estacion": "1024E",  # San Sebastián / Igueldo (o "1014A" para el Aeropuerto)
        "aemet_municipio": "20069", # San Sebastián
        "prefijo_archivos_aemet": "aemet_urumea",
        
        # 3. Parámetros Hidrológicos (Confederaciones / SAIH)
        "sai_estacion_id": "C0F0",  # Estación de Ereñozu (Euskalmet)
        "sai_api_tipo": "euskalmet",
        "archivo_salida_hidro": "urumea_hidro_actual.csv",
        "euskalmet_sensor_id": "CAF0", # Habitualmente coincide con el ID de estación o el canal físico
        "euskalmet_measure_type_id": "measuresForWater",
        "euskalmet_measure_id": "flow_1",
        "euskalmet_url_historico_base": "https://opendata.euskadi.eus/contenidos/ds_meteorologicos/met_stations_ds_{ano}/opendata/{ano}/{estacion}/{estacion}_{ano}_1.xml",
        "carpeta_hidro_h": "data/input/hidro_h/pais_vasco/"
    },
    
    "besaya": {
        "nombre_legible": "Río Besaya (Cantabria)",
        "prefijo_archivos": "besaya",
        
        # 1. Parámetros Copernicus (ERA5-Land y GloFAS)
        "coor_copernicus": [43.50, -4.80, 42.70, -3.10], 
        "puntos_openmeteo": {
            "Cabecera": (43.05, -4.08),
            "Tramo_Medio": (43.20, -4.10),
            "Desembocadura": (43.35, -4.05)
        },
        "archivo_salida_openmeteo": "openmeteo_besaya_forecast_areal.csv",
        "carpeta_caudal_h": "data/input/caudal_h/cantabria/",
        "prefijo_fichero_caudal_h": "caudal_historico",
        "carpeta_lluvia_h": "data/input/lluvia_h/cantabria/",
        "prefijo_fichero_lluvia_h": "lluvia_historica",
        
        # 2. Parámetros AEMET (Estación de Referencia e Inferencia)
        "aemet_estacion": "1109X",  # Santander Aeropuerto
        "aemet_municipio": "39087", # Torrelavega
        "prefijo_archivos_aemet": "aemet_besaya",
        
        # 3. Parámetros Hidrológicos (Confederaciones / SAIH)
        "sai_estacion_id": "A085",  # Estación de aforo del Besaya (SAIH Cantábrico)
        "sai_api_tipo": "cantabrico",
        "archivo_salida_hidro": "besaya_hidro_actual.csv",
        "carpeta_hidro_h": "data/input/hidro_h/cantabria/"
    }
}