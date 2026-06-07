# descargar_historico_real.py
import os
import time
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timedelta
from utils_adquisicion_datos import obtener_argumentos_y_config

def descargar_historico_urumea(parametros, destino_final):
    """Rama País Vasco: Descarga y parsea los XML anuales masivos de Open Data Euskadi."""
    print("🛰️  Conectando con el repositorio de archivos anuales de Open Data Euskadi...")
    
    estacion = parametros.get("sai_estacion_id", "C0F0")
    url_template = "https://opendata.euskadi.eus/contenidos/ds_meteorologicos/met_stations_ds_{ano}/opendata/{ano}/{estacion}/{estacion}_{ano}_1.xml"
    
    ano_actual = datetime.now().year
    registros_totales = []

    for ano in range(2020, ano_actual + 1):
        url_xml = url_template.format(ano=ano, estacion=estacion)
        print(f"   -> Descargando año {ano}...")
        try:
            res = requests.get(url_xml, timeout=30)
            if res.status_code != 200:
                print(f"      ⚠️ Archivo no disponible para el año {ano}. Saltando...")
                continue
                
            root = ET.fromstring(res.content)
            for dia_nodo in root.findall('.//dia'):
                fecha_base = dia_nodo.get('Dia')
                
                for hora_nodo in dia_nodo.findall('.//hora'):
                    hora_base = hora_nodo.get('Hora')
                    meteoros = hora_nodo.find('.//Meteoros')
                    
                    if meteoros is not None:
                        caudal_nodo = meteoros.find('Caudal2._a_0cm')
                        nivel_nodo = meteoros.find('Nivel2._a_0cm')
                        
                        caudal_val = float(caudal_nodo.text) if caudal_nodo is not None and caudal_nodo.text else None
                        nivel_val = float(nivel_nodo.text) if nivel_nodo is not None and nivel_nodo.text else None
                        
                        if caudal_val is None and nivel_val is None:
                            continue
                            
                        registros_totales.append({
                            "fecha_hora": f"{fecha_base} {hora_base}:00",
                            "caudal_m3s": caudal_val,
                            "nivel_m": nivel_val
                        })
        except Exception as e:
            print(f"      ❌ Error procesando el año {ano}: {e}")

    if registros_totales:
        df_historico = pd.DataFrame(registros_totales)
        df_historico['fecha_hora'] = pd.to_datetime(df_historico['fecha_hora'])
        df_horario = df_historico.groupby(df_historico['fecha_hora'].dt.floor('h')).mean(numeric_only=True).reset_index()
        df_horario = df_horario.sort_values('fecha_hora').reset_index(drop=True)
        
        df_horario.to_csv(destino_final, index=False)
        print(f"🏆 ¡ÉXITO! Serie unificada del Urumea guardada en: {destino_final}")
    else:
        print("❌ No se pudieron extraer datos para el Urumea.")


def descargar_historico_besaya_api(parametros, credenciales, destino_final):
    """Rama Cantabria: Extrae vectores paralelos de la API y los consolida a resolución horaria."""
    print("📡 Conectando con la API del SAIH Cantábrico...")
    
    api_key = str(credenciales.get("SAI_API_KEY", "")).strip()
    estacion_id = parametros.get("saih_cantabrico_id_estacion_num", 375)
    
    base_url = f"https://opendata.saichcantabrico.es/sai-pub-api/api/estacion/{estacion_id}/senal/1/serie"
    
    headers = {
        "X-API-KEY": api_key,
        "accept": "application/json"
    }
    
    # Ventana temporal completa del TFM
    fecha_actual = datetime(2020, 1, 1)
    fecha_fin = datetime.now()
    
    dfs_mensuales = []
    print("📊 Iniciando descarga secuencial por meses...")
    
    while fecha_actual < fecha_fin:
        desde_str = fecha_actual.strftime("%Y-%m-%dT00:00:00")
        
        if fecha_actual.month == 12:
            proximo_mes = datetime(fecha_actual.year + 1, 1, 1)
        else:
            proximo_mes = datetime(fecha_actual.year, fecha_actual.month + 1, 1)
            
        hasta_dt = proximo_mes - timedelta(seconds=1)
        if hasta_dt > fecha_fin:
            hasta_dt = fecha_fin
        hasta_str = hasta_dt.strftime("%Y-%m-%dT%H:%M:%S")
        
        print(f"      -> Descargando: {desde_str} al {hasta_str}")
        params = {"desde": desde_str, "hasta": hasta_str}
        
        try:
            res = requests.get(base_url, headers=headers, params=params, timeout=30)
            
            if res.status_code == 429:
                tiempo_espera = int(res.headers.get("X-Rate-Limit-Retry-After-Seconds", 15))
                print(f"         ⚠️ Rate Limit alcanzado. Esperando {tiempo_espera}s...")
                time.sleep(tiempo_espera)
                res = requests.get(base_url, headers=headers, params=params, timeout=30)
                
            if res.status_code == 200:
                json_data = res.json()
                
                # Mapeo de vectores paralelos usando las llaves del JSON descubierto
                if isinstance(json_data, dict) and "timestamps" in json_data and "valores" in json_data:
                    list_times = json_data["timestamps"]
                    list_vals = json_data["valores"]
                    
                    if len(list_times) > 0:
                        df_mes = pd.DataFrame({
                            "fecha_hora": pd.to_datetime(list_times),
                            "nivel_m": list_vals
                        })
                        
                        # Limpieza de nulos y ordenación temporal antes de resamplear
                        df_mes = df_mes.dropna(subset=["fecha_hora"]).sort_values("fecha_hora")
                        
                        # ⏳ COMPRESIÓN HORARIA: Pasamos de 5 min a 1 hora (Media aritmética)
                        df_mes_horario = df_mes.groupby(df_mes['fecha_hora'].dt.floor('h')).mean(numeric_only=True).reset_index()
                        
                        dfs_mensuales.append(df_mes_horario)
                        print(f"         ✅ OK: {len(list_times)} registros agregados a {len(df_mes_horario)} horas.")
                    else:
                        print("         🟧 Mes sin lecturas en el servidor.")
                else:
                    print("         ⚠️ Estructura JSON inesperada en este tramo.")
            else:
                print(f"         ❌ Error HTTP {res.status_code}: {res.text.strip()}")
                
        except Exception as e:
            print(f"         ❌ Fallo procesando bloque: {e}")
            
        # Retardo estructural estricto para cuidar la API
        time.sleep(11)
        fecha_actual = proximo_mes

    # Consolidación final de la serie histórica
    if dfs_mensuales:
        df_final = pd.concat(dfs_mensuales, ignore_index=True)
        df_final = df_final.sort_values('fecha_hora').reset_index(drop=True)
        
        # Añadimos la columna caudal vacía para asegurar la simetría estructural con el País Vasco
        df_final['caudal_m3s'] = None
        
        # Reordenamos las columnas idéntico al Urumea
        df_final = df_final[['fecha_hora', 'caudal_m3s', 'nivel_m']]
        
        df_final.to_csv(destino_final, index=False)
        print(f"\n🏆 Serie histórica unificada en metros del Besaya guardada en:")
        print(f"   -> {destino_final}")
    else:
        print("❌ El pipeline terminó sin recopilar registros.")


if __name__ == "__main__":
    id_cuenca, parametros, credenciales = obtener_argumentos_y_config()
    
    print(f"=====================================================================")
    print(f"🌊 PIPELINE UNIFICADO DE HIDROLOGÍA HISTÓRICA REAL")
    print(f"🦅 Objetivo: {parametros.get('nombre_legible', id_cuenca)}")
    print(f"=====================================================================\n")
    
    carpeta_destino = parametros.get("carpeta_hidro_h")
    if not carpeta_destino:
        carpeta_destino = parametros.get("carpeta_caudal_h", f"data/input/caudal_h/{id_cuenca}/")
        
    prefijo_fichero = parametros.get("prefijo_fichero_caudal_h", "caudal_historico")
    os.makedirs(carpeta_destino, exist_ok=True)
    nombre_salida = os.path.join(carpeta_destino, f"{prefijo_fichero}_real_completo.csv")
    
    if id_cuenca == "urumea":
        descargar_historico_urumea(parametros, nombre_salida)
    elif id_cuenca == "besaya":
        descargar_historico_besaya_api(parametros, credenciales, nombre_salida)
    else:
        print(f"❌ Error: La cuenca '{id_cuenca}' no está soportada.")