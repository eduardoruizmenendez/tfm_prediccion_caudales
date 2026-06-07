import cdsapi
import os
import pandas as pd
import time
from datetime import datetime
from utils_adquisicion_datos import obtener_argumentos_y_config, procesar_netcdf_a_dataframe

# =====================================================================
# 1. CREDENCIALES PORTAL EWDS (GLOFAS)
# =====================================================================
def configurar_credenciales_ewds():
    """Garantiza la existencia del archivo .cdsapirc para el portal EWDS."""
    ruta_rc = os.path.expanduser('~/.cdsapirc')
    with open(ruta_rc, 'w') as f:
        f.write('url: https://ewds.climate.copernicus.eu/api\n')
        f.write('key: b1c8ed63-d58a-4ca0-b6a8-0068ce339221')

# =====================================================================
# 2. PROCESAMIENTO DE UN MES ESPECÍFICO
# =====================================================================
def descargar_mes_caudal(year, month, parametros):
    """Descarga un mes específico respetando la configuración de la cuenca."""
    
    # Extraemos las rutas y variables EXACTAS del archivo de configuración
    carpeta_destino = parametros["carpeta_caudal_h"]
    prefijo_fichero = parametros["prefijo_fichero_caudal_h"]
    coordenadas = parametros["coor_copernicus"]
    
    # Aseguramos que la carpeta de la cuenca exista
    os.makedirs(carpeta_destino, exist_ok=True)
    
    # Construcción exacta de la ruta
    nombre_csv = f"{carpeta_destino}{prefijo_fichero}_{year}_{month:02d}.csv"
    
    # Control de duplicados para no volver a descargar meses pasados
    fecha_hoy = datetime.now()
    if os.path.exists(nombre_csv) and not ((year == fecha_hoy.year) and (month == fecha_hoy.month)):
        print(f"   ⏭️ El archivo {nombre_csv} ya existe. Saltando descarga.")
        return True

    print(f"   📡 Descargando caudales desde Copernicus para {year}-{month:02d}...")
    c = cdsapi.Client()
    archivo_nc = "temp_caudal.nc"
    
    if os.path.exists(archivo_nc):
        os.remove(archivo_nc)
        
    # Construcción de los días del mes
    dias_del_mes = [f"{i:02d}" for i in range(1, 32)] 
    if month in [4, 6, 9, 11]: dias_del_mes = dias_del_mes[:-1]
    if month == 2: 
        # Ajuste por años bisiestos simple
        dias_del_mes = dias_del_mes[:-3] if (year % 4 == 0) else dias_del_mes[:-2]
    
    if year == fecha_hoy.year and (fecha_hoy.month - month) <= 4:
        tipo_producto = "intermediate"
    else:
        tipo_producto = "consolidated"
    
    peticion = {
        "system_version": ["version_4_0"],
        "hydrological_model": ["lisflood"],
        "product_type": [tipo_producto],
        "variable": ["river_discharge_in_the_last_24_hours"],
        "hyear": [str(year)],
        "hmonth": [f"{month:02d}"],
        "hday": dias_del_mes,
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": coordenadas # Inyección dinámica de la Bounding Box de la cuenca
    }

    try:
        # Descarga el temporal NetCDF
        c.retrieve('cems-glofas-historical', peticion).download(archivo_nc)
        
        # Procesamos el NetCDF usando la función que extrae la media de la cuenca
        # y nos devuelve el DataFrame limpio
        df_limpio = procesar_netcdf_a_dataframe(
            ruta_netcdf=archivo_nc,
            coordenadas=coordenadas,
            variable_objetivo='dis24', # Variable nativa de GloFAS
            renombrar_columna='caudal_m3s'
        )
        
        if df_limpio is not None:
            # Eliminamos filas sin datos (tierra seca) y guardamos en tu formato original
            df_limpio = df_limpio.dropna(subset=['caudal_m3s'])
            df_limpio.to_csv(nombre_csv, index=False)
            print(f"   ✅ Guardado con éxito: {nombre_csv}")
            
        # Limpieza del archivo temporal
        if os.path.exists(archivo_nc):
            os.remove(archivo_nc)
            
        return True

    except Exception as e:
        print(f"   ❌ Error descargando {year}-{month:02d}: {e}")
        if os.path.exists(archivo_nc):
            os.remove(archivo_nc)
        return False

# =====================================================================
# 3. BUCLE PRINCIPAL (ORQUESTADO POR CLI)
# =====================================================================
if __name__ == "__main__":
    # Sincronizamos las credenciales del portal EWDS
    configurar_credenciales_ewds()
    
    # Extraemos el identificador y los parámetros del archivo de configuración global
    id_cuenca, parametros, _ = obtener_argumentos_y_config()
    
    print(f"🚀 INICIANDO EXTRACCIÓN DIARIA DE CAUDALES PARA: {parametros['nombre_legible']}")
    
    fecha_hoy = datetime.now()
    anos_a_descargar = range(2020, fecha_hoy.year + 1)
    meses_a_descargar = range(1, 13)
    
    for ano in anos_a_descargar:
        for mes in meses_a_descargar:
            # Si el mes está en el futuro respecto a hoy, rompemos el bucle
            if ano == fecha_hoy.year and mes > fecha_hoy.month:
                break
                
            exito = descargar_mes_caudal(ano, mes, parametros)
            
            time.sleep(4)