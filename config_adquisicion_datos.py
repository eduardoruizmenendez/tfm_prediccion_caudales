# =====================================================================
# CONFIGURACIÓN CENTRALIZADA MULTI-API PARA EL PIPELINE HIDROLÓGICO
# =====================================================================

AEMET_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJlZHVhcmRvcnVpem1lbmVuZGV6QGdtYWlsLmNvbSIsImp0aSI6ImVhNDJmOWFiLTUwMTYtNDExMi1iZGU2LWRiNTM3ZTNiOWNkOSIsImlzcyI6IkFFTUVUIiwiaWF0IjoxNzc2MDEzOTQxLCJ1c2VySWQiOiJlYTQyZjlhYi01MDE2LTQxMTItYmRlNi1kYjUzN2UzYjljZDkiLCJyb2xlIjoiIn0.gG2YSKhKkF5gy6hk0ePpbjoR7uIqvJz72EK-g0SD1Vg"

EUSKALMET_API_KEY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC0v4Os3dUbL4zknDO5yab1JfKqfLtpy91Qt/Ci/dxR+lyC4ZiNpaMFn3eyfGOLuOKRmGD8OTCcbW9Ngyb9nP1sdCf3vjdBH2IAPlt91s9+FgwbVJ2k7B3toSjsuG7JKnHTRAfqffj4M8MHLzYbkDdfTQo8n1dd+d06VznwKzgq4BXzDDXasJgU02QF2bKrS4h0xFE+CrxKprF8ELNaD07KWW5aCElhHDnUAK1M3fUoAxGb6FvKDljXF+Y9DGfwaujwUdMJ9HFSypq1AVX9r1CW+LzgCMajX4lonWgQOJ0AZWHu1T5RcaEtp+IH2hzJ6d8D5n4eWdCyRifzjgmDAqnlAgMBAAECggEAPq/bUbWAJxUXRuRb1jg3ZPeb0YBAGaHAaLHazhTAeFgeBLCMUbgcMaOMhoU4mylsvvU70c5d6yrTOu1dNQFhLV+dywEYNchWG2KFJcA+J2srGMGAiUXw3U0THgKbPb6wSobiPfQhyKdfIRtBJ08dvTpBbiQPT4MMtKKy7/Z1XPzUUfYwT8OSOKX8sK2ywXrscR/ITRIadO9wZaSQ4y0WXq6X1cxVIbzETi1ogaeX2VBCR5g6qAxIR6nzMgnfCRKxpdivYhQAR3ARkAZXoBdJjOc6zBP/CX0TeYWuq5RyABPjF25kcYrPmCgDf8y/rtu+sn9YI21W3kBow21al7YBswKBgQDnm8qpchDUSSshb6oq+ZUGztk5Kr8Fspa5gqEBqktWxpHSmm5wyzwr/zvYMtAEX0j707Ln9cGWNQ+elZlJV0t2mspMPhtR4VXyVaa5c9GW3iTH5rEG7WIxC9gav3utrU+6g6502yd3BkdFwdZfu+m7UMu5hXB7eS2iTBJFcjKkrwKBgQDHyIQAintOl2Oy9GgcJf6iiQVWYiSKZG83GKnBBK6xU2c29rEIEDsXbvG62lbRLQKwt1Nbtlo8/9DeN3TRw2ay52FR+djcGO5ZAHWhJVQv4P5xpporpicY3eAiOemXYjNehYHCP7lG+GYMda0nuXCFHvaVmY2+zlfKjo09c2gnqwKBgFU60nBahnDoYBPU2MUpxTqVIgDUhykcmDS6Km/HcCQFvKHIrL2bPJBgQ3CC+mOxgNUTCXIs0Mlqy02rdZY0ppOF0M4PyNPv3UXpWQpD4avoIZbigOCwuIKd/i+RqXy3G3Dihm+AOlylldLIyw+9wfxpdh7WSRdW94ETB2JA7PwHAoGBAL+d2M3UBNSqa1uXA8wLvSETnuTtmPKLxgfoRdj1rsAxqIuVLNL5DlQ5euymwiI6s5vfGbqbOg3Lpv+b3RXb/sKVHkjMBG2GFAWVZT08WnTZrfI/wxseb91v4auyNBOYgoCkOIKhMAmb8fT9YSj6uatUuVlfQA7ERnvnIhzQdhOlAoGAZDAJSSu4MrD4VslrXXxdKEl0nniq3B4U+lawdjhUxqKivmHRwFvbz0QZRI3VgaFfmjBD5CXz8s0MdgVcannrFadCNsIeogPLmPiNPo2WusKI5A+w4qAbStw31maz2ZYQAfi4YKJ63xba7jSzQq0jlljWuPs57VAluXVwpWKglVY="

SAI_API_KEY_CANTABRICO = "aXZhbi5hcmFraXN0YWluQHRlY25hbGlhLmNvbTpVbmRmQlpob0pscTRZMUhEWkR1NQ=="

CONFIGURACION_CUENCAS = {
    "urumea": {
        "nombre_legible": "Río Urumea (País Vasco)",
        "prefijo_archivos": "urumea",
        
        # 1. Parámetros Copernicus (ERA5-Land y GloFAS)
        "coor_copernicus": [43.35, -2.05, 43.10, -1.75], 
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