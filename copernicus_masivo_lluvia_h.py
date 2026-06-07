import cdsapi
import os
import pandas as pd
import time
from datetime import datetime
from utils_adquisicion_datos import obtener_argumentos_y_config, procesar_netcdf_a_dataframe

# =====================================================================
# 1. CREDENCIALES PORTAL CLIMÁTICO CENTRAL (ERA5-LAND)
# =====================================================================
def configurar_credenciales_cds():
    """Garantiza la existencia del archivo .cdsapirc para el portal central de Copernicus."""
    ruta_rc = os.path.expanduser('~/.cdsapirc')
    with open(ruta_rc, 'w') as f:
        f.write('url: https://cds.climate.copernicus.eu/api\n')
        f.write('key: b1c8ed63-d58a-4ca0-b6a8-0068ce339221')

# =====================================================================
# 2. PROCESAMIENTO MENSUAL DE REANÁLISIS ERA5
# =====================================================================
def descargar_mes_lluvia(year, month, parametros):
    """Descarga un mes de lluvia y temperatura respetando las rutas por cuenca."""
    
    # EXTRAE DIRECTAMENTE LAS CLAVES DE LA CONFIGURACIÓN CENTRALIZADA
    carpeta_destino = parametros["carpeta_lluvia_h"]
    prefijo_fichero = parametros["prefijo_fichero_lluvia_h"]
    coordenadas = parametros["coor_copernicus"]
    
    # Aseguramos la existencia física del subdirectorio definido 
    os.makedirs(carpeta_destino, exist_ok=True)
    
    # Construcción limpia y exacta de la ruta:
    # ej. "data/input/lluvia_h/pais_vasco/lluvia_historica_2020_01.csv"
    nombre_csv = f"{carpeta_destino}{prefijo_fichero}_{year}_{month:02d}.csv"
    
    # Evitamos re-descargas innecesarias de meses consolidados en el pasado
    fecha_hoy = datetime.now()
    if os.path.exists(nombre_csv) and not ((year == fecha_hoy.year) and (month == fecha_hoy.month)):
        print(f"   Skip: El archivo {nombre_csv} ya existe. Saltando descarga.")
        return True

    print(f"   📡 Conectando a ERA5-Land para el intervalo {year}-{month:02d}...")
    c = cdsapi.Client()
    archivo_nc = "temp_descarga.nc"
    
    if os.path.exists(archivo_nc):
        os.remove(archivo_nc)
        
    # Construcción analítica de la lista de días
    dias_del_mes = [f"{i:02d}" for i in range(1, 32)] 
    if month in [4, 6, 9, 11]: 
        dias_del_mes = dias_del_mes[:-1]
    if month == 2: 
        dias_del_mes = dias_del_mes[:-3] if (year % 4 == 0) else dias_del_mes[:-2]
    
    peticion = {
        'variable': ['total_precipitation', '2m_temperature'],
        'year': str(year),
        'month': f"{month:02d}",
        'day': dias_del_mes,
        'time': [f"{i:02d}:00" for i in range(24)], # Vector horario completo
        'area': coordenadas,
        "data_format": "netcdf",
        "download_format": "unarchived"
    }

    try:
        # Llamada a la infraestructura de Copernicus Climate
        c.retrieve('reanalysis-era5-land', peticion, archivo_nc)
        
        # Procesamos el cubo NetCDF usando las utilidades para extraer la media
        df_precipitacion = procesar_netcdf_a_dataframe(
            ruta_netcdf=archivo_nc,
            coordenadas=coordenadas
           # variable_objetivo='tp',
           # renombrar_columna='tp'
        )
        
        if df_precipitacion is not None:
            # Eliminamos posibles registros nulos geográficos (píxeles sobre el mar)
            df_precipitacion = df_precipitacion.dropna(subset=['tp'])
            
            # Guardamos la tabla resultante en la ruta mapeada
            df_precipitacion.to_csv(nombre_csv, index=False)
            print(f"   ✅ Guardado con éxito: {nombre_csv}")
            
        if os.path.exists(archivo_nc):
            os.remove(archivo_nc)
            
        return True

    except Exception as e:
        print(f"   ❌ Error en el proceso de ingesta de {year}-{month:02d}: {e}")
        if os.path.exists(archivo_nc):
            os.remove(archivo_nc)
        return False

# =====================================================================
# 3. ORQUESTACIÓN Y BUCLE CRONOLÓGICO POR LÍNEA DE COMANDOS
# =====================================================================
if __name__ == "__main__":
    
    # Extraemos el identificador y los parámetros mediante el parser CLI
    id_cuenca, parametros, _ = obtener_argumentos_y_config()
    
    # Aseguramos el token del servidor CDS climático central
    configurar_credenciales_cds()
    
    print(f"🚀 INICIANDO REANÁLISIS DE PRECIPITACIONES HISTÓRICAS: {parametros['nombre_legible']}")
    
    fecha_hoy = datetime.now()
    anos_a_descargar = range(2020, fecha_hoy.year + 1)
    meses_a_descargar = range(1, 13)
    
    for ano in anos_a_descargar:
        for mes in meses_a_descargar:
            # Control de desbordamiento en el año en curso
            if ano == fecha_hoy.year and mes > fecha_hoy.month:
                break
                
            exito = descargar_mes_lluvia(ano, mes, parametros)
            
            ruta_comprobacion = f"{parametros['carpeta_lluvia_h']}{parametros['prefijo_fichero_lluvia_h']}_{ano}_{mes:02d}.csv"
            if exito and not os.path.exists(ruta_comprobacion):
                time.sleep(10)