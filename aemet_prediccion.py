import requests
import pandas as pd
from datetime import datetime
from utils_adquisicion_datos import hacer_peticion_robusta, obtener_argumentos_y_config

# =====================================================================
# FUNCIÓN DE EXTRACCIÓN Y PARSEO
# =====================================================================
def descargar_prediccion_horaria(api_key, id_municipio, prefijo):
    
    print(f"📡 Conectando con AEMET (Predicción Futura) para el municipio {id_municipio}...")
    
    url_peticion = f"https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio/horaria/{id_municipio}"
    querystring = {"api_key": api_key}
    headers = {'cache-control': "no-cache"}
    
    # PASO 1: Petición con reintentos
    res_1 = hacer_peticion_robusta(url_peticion, headers=headers, params=querystring)
    
    if res_1 is None:
        return None # Salimos si fallaron todos los reintentos
        
    datos_res_1 = res_1.json()
    
    if datos_res_1.get('estado') == 200:
        url_datos = datos_res_1.get('datos')
        print("✅ Permiso concedido. Descargando predicción multiparamétrica...")
        
        # PASO 2: Segunda petición robusta para descargar el JSON pesado
        res_2 = hacer_peticion_robusta(url_datos, timeout=30)
        
        if res_2 is None:
            return None
            
        datos_brutos = res_2.json()
        
        # --- INICIO DEL PARSEO ---
        dias_prediccion = datos_brutos[0]['prediccion']['dia']
        filas_limpias = []
        
        for dia in dias_prediccion:
            fecha_base = dia['fecha'][:10]
            datos_por_hora = {}
            
            for p in dia.get('precipitacion', []):
                hora = p.get('periodo')
                if hora and len(hora) == 2:
                    val = p.get('value')
                    datos_por_hora.setdefault(hora, {})['precipitacion_prevista'] = float(val) if val != 'Ip' and val else 0.0

            for prob in dia.get('probPrecipitacion', []):
                periodo = prob.get('periodo')
                val = prob.get('value')
                
                if periodo and val != '':
                    prob_val = int(val)
                    if len(periodo) == 2:
                        datos_por_hora.setdefault(periodo, {})['prob_precipitacion'] = prob_val
                    elif len(periodo) == 4:
                        h_inicio, h_fin = int(periodo[0:2]), int(periodo[2:4])
                        for h in range(h_inicio, h_fin):
                            hora_str = f"{h:02d}"
                            datos_por_hora.setdefault(hora_str, {})['prob_precipitacion'] = prob_val

            for t in dia.get('temperatura', []):
                hora = t.get('periodo')
                if hora and len(hora) == 2:
                    val = t.get('value')
                    datos_por_hora.setdefault(hora, {})['temperatura_prevista'] = float(val) if val else None

            for hora, valores in datos_por_hora.items():
                registro = {
                    'fecha_hora': f"{fecha_base} {hora}:00:00",
                    'precipitacion_prevista': valores.get('precipitacion_prevista', 0.0),
                    'prob_precipitacion': valores.get('prob_precipitacion', 0),
                    'temperatura_prevista': valores.get('temperatura_prevista', None)
                }
                filas_limpias.append(registro)
                
        # --- FIN DEL PARSEO ---
                
        df_pred = pd.DataFrame(filas_limpias)
        df_pred['fecha_hora'] = pd.to_datetime(df_pred['fecha_hora'])
        df_pred = df_pred.sort_values('fecha_hora').reset_index(drop=True)
        
        nombre_csv = f"{prefijo}_{id_municipio}_prediccion.csv"
        df_pred.to_csv(nombre_csv, index=False)
        print(f"💾 ¡Éxito! Predicción guardada en {nombre_csv}")
        
        return df_pred
            
    else:
        print(f"❌ Error interno de AEMET: {datos_res_1.get('descripcion')}")
        return None

# =====================================================================
# 4. EJECUCIÓN 
# =====================================================================
if __name__ == "__main__":
    
    # Desestructuramos los tres valores que devuelve la utilidad unificada
    id_cuenca, parametros, credenciales = obtener_argumentos_y_config()
    
    MUNICIPIO = parametros["aemet_municipio"]
    PREFIJO = parametros["prefijo_archivos_aemet"]
    
    print(f"🚀 INICIANDO ENTORNO OPERATIVO PARA: {parametros['nombre_legible']}")
    df_futuro = descargar_prediccion_horaria(credenciales["AEMET"], MUNICIPIO, PREFIJO)
    
    if df_futuro is not None:
        print(f"\nResumen: {len(df_futuro)} horas hacia el futuro descargadas.")
        print(df_futuro.head(3))

