import requests
import json
import pandas as pd
import time
from datetime import datetime
from utils_adquisicion_datos import hacer_peticion_robusta, obtener_argumentos_y_config

# =====================================================================
# FUNCIÓN MAESTRA DE EXTRACCIÓN HISTÓRICA SEMESTRAL
# =====================================================================
def extraer_historico_multi_semestre(api_key, id_estacion, prefijo, ano_inicio=2020):
    ano_actual = datetime.now().year
    headers = {'cache-control': "no-cache"}
    querystring = {"api_key": api_key}
    
    dataframes_periodos = []
    
    print(f"🚀 INICIANDO EXTRACCIÓN HISTÓRICA SEGMENTADA EN SEMESTRES ({ano_inicio}-{ano_actual})")
    
    for ano in range(ano_inicio, ano_actual + 1):
        # Segmentamos el año en dos bloques para respetar el límite estricto de 6 meses por petición
        periodos = [
            {"nombre": f"{ano} - Semestre 1", "ini": f"{ano}-01-01T00:00:00UTC", "fin": f"{ano}-06-30T23:59:59UTC"},
            {"nombre": f"{ano} - Semestre 2", "ini": f"{ano}-07-01T00:00:00UTC", "fin": f"{ano}-12-31T23:59:59UTC"}
        ]
        
        for p in periodos:
            # Si el intervalo temporal pertenece al futuro, el orquestador lo descarta
            fecha_ini_dt = datetime.strptime(p["ini"][:10], "%Y-%m-%d")
            if fecha_ini_dt > datetime.now():
                continue
                
            # Si el fin del semestre supera el día de hoy, capamos el rango a la fecha actual exacta
            if datetime.strptime(p["fin"][:10], "%Y-%m-%d") > datetime.now():
                p["fin"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SUTC")
                
            print(f"\n📅 Procesando intervalo: {p['nombre']}...")
            url_peticion = f"https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/fechaini/{p['ini']}/fechafin/{p['fin']}/estacion/{id_estacion}"
            
            # PASO 1: Solicitud del enlace temporal con reintentos robustos
            res_1 = hacer_peticion_robusta(url_peticion, headers=headers, params=querystring)
            if res_1 is None:
                print(f"⏩ Saltando {p['nombre']} por indisponibilidad del servidor principal.")
                continue
                
            datos_res_1 = res_1.json()
            
            if datos_res_1.get('estado') == 200:
                url_datos = datos_res_1.get('datos')
                
                # Pausa técnica de control de ráfaga antes de la descarga masiva
                time.sleep(2)
                
                # PASO 2: Descarga del payload JSON con los registros climáticos diarios
                res_2 = hacer_peticion_robusta(url_datos, timeout=30) # Timeout ampliado para bloques pesados
                if res_2 is None:
                    continue
                    
                datos_reales = res_2.json()
                df_periodo = pd.DataFrame(datos_reales)
                
                if not df_periodo.empty:
                    print(f"   ✅ Extraídos {len(df_periodo)} registros correctamente.")
                    dataframes_periodos.append(df_periodo)
                
                # Protocolo Anti-Throttling obligatorio para proteger la IP de bloqueos
                time.sleep(3)
            else:
                print(f"   ⚠️ AEMET denegó el intervalo: {datos_res_1.get('descripcion')}")
                
    # Procesamiento y consolidación de la serie temporal unificada
    if dataframes_periodos:
        print("\n🧱 Unificando bloques semestrales y depurando la serie temporal...")
        df_completo = pd.concat(dataframes_periodos, ignore_index=True)
        
        # Transformación analítica y homogenización de etiquetas (Capa Silver)
        df_limpio = df_completo[['fecha', 'prec', 'tmed']].copy()
        df_limpio.rename(columns={'fecha': 'fecha_hora'}, inplace=True)
        
        # Limpieza de tipos de datos conflictivos de AEMET (Lluvia inapreciable 'Ip' y comas decimales)
        df_limpio['prec'] = df_limpio['prec'].replace('Ip', '0.0')
        df_limpio['prec'] = df_limpio['prec'].str.replace(',', '.').astype(float)
        df_limpio['tmed'] = df_limpio['tmed'].str.replace(',', '.').astype(float)
        
        # Eliminación estricta de solapes temporales y ordenación cronológica final
        df_limpio = df_limpio.drop_duplicates(subset=['fecha_hora']).sort_values('fecha_hora').reset_index(drop=True)
        
        return df_limpio
    else:
        return None

# =====================================================================
# INTERFAZ POR LÍNEA DE COMANDOS (CLI)
# =====================================================================
if __name__ == "__main__":
    # Desestructuramos la configuración global unificada desde el módulo Utils
    id_cuenca, parametros, credenciales = obtener_argumentos_y_config()
    
    ESTACION = parametros["aemet_estacion"]
    PREFIJO = parametros["prefijo_archivos_aemet"]
    
    print(f"🦅 Cuenca de trabajo validada: {parametros['nombre_legible']}")
    
    # Lanzamos el pipeline de extracción multianual desde 2020
    df_historico_total = extraer_historico_multi_semestre(credenciales["AEMET"], ESTACION, PREFIJO, ano_inicio=2020)
    
    if df_historico_total is not None:
        # Generación dinámica del nombre de archivo unificado
        nombre_csv = f"{PREFIJO}_{ESTACION}_historicos.csv"
        df_historico_total.to_csv(nombre_csv, index=False)
        
        print(f"\n✅ ¡PIPELINE DE INGESTA HISTÓRICA CONSOLIDADO!")
        print(f"💾 Archivo maestro indexado en: {nombre_csv}")
        print(f"📊 Dimensiones finales de la matriz: {len(df_historico_total)} días integrados.")
        print(df_historico_total.head(2))
        print("...")
        print(df_historico_total.tail(2))
    else:
        print("\n❌ Error del sistema: Las restricciones operativas impidieron consolidar el histórico.")