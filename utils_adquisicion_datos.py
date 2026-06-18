import requests
import time
import argparse
import xarray as xr
import pandas as pd
import jwt
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from config_adquisicion_datos import CONFIGURACION_CUENCAS

# =====================================================================
# UTILIDAD 1: GESTIÓN DE PETICIONES HTTP ROBUSTAS
# =====================================================================
def hacer_peticion_robusta(url, headers=None, params=None, max_reintentos=3, timeout=15):
    """Ejecuta una petición HTTP con reintentos automáticos ante micro-cortes."""
    for intento in range(1, max_reintentos + 1):
        try:
            respuesta = requests.get(url, headers=headers, params=params, timeout=timeout)
            respuesta.raise_for_status()
            return respuesta
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ [Intento {intento}/{max_reintentos}] Incidencia en la red externa: {e}")
            if intento < max_reintentos:
                print("   ⏳ Esperando 5 segundos para el próximo reintento...")
                time.sleep(5)
            else:
                print("   ❌ Se agotaron los reintentos permitidos. Servidor inaccesible.")
                return None

# =====================================================================
# UTILIDAD 2: PARSEADOR CLI ESTÁNDAR
# =====================================================================
def obtener_argumentos_y_config():
    """Configura el menú CLI mediante argparse y retorna los parámetros de la cuenca."""
    parser = argparse.ArgumentParser(
        description="Core Orquestador del Pipeline de Ingesta Hidrometeorológica."
    )
    
    opciones_validas = list(CONFIGURACION_CUENCAS.keys())
    
    parser.add_argument(
        "--cuenca",
        type=str,
        required=True,
        choices=opciones_validas,
        help="Clave identificadora de la cuenca hidrográfica a procesar."
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    
    credenciales = {
        "AEMET": os.getenv("AEMET_API_KEY"),
        "EUSKALMET": os.getenv("EUSKALMET_API_KEY"),
        "SAI_API_KEY": os.getenv("SAI_API_KEY_CANTABRICO")
    }
    
    # Retorna tanto el string ('urumea'/'besaya') como el diccionario de parámetros específico
    return args.cuenca, CONFIGURACION_CUENCAS[args.cuenca], credenciales

# =====================================================================
# UTILIDAD 3: PROCESAMIENTO ANALÍTICO DE NETCDF MULTIVARIABLE (CORREGIDO)
# =====================================================================
def procesar_netcdf_a_dataframe(ruta_netcdf, coordenadas):
    """
    Recorta espacialmente un archivo NetCDF según una Bounding Box, 
    calcula la media espacial de la cuenca para TODAS las variables presentes 
    y lo transforma en un DataFrame limpio.
    """
    import xarray as xr
    import pandas as pd
    
    print(f"📦 Abriendo y procesando matriz multidimensional: {ruta_netcdf}")
    
    # Desestructuramos la caja delimitadora de la cuenca [Norte, Oeste, Sur, Este]
    norte, oeste, sur, este = coordenadas
    
    try:
        # Cargamos el dataset con xarray
        with xr.open_dataset(ruta_netcdf) as ds:
            # 1. Recorte espacial (Slicing) adaptándose a la orientación de las latitudes de Copernicus
            if ds.latitude.values[0] > ds.latitude.values[-1]:
                ds_recortado = ds.sel(latitude=slice(norte, sur), longitude=slice(oeste, este))
            else:
                ds_recortado = ds.sel(latitude=slice(sur, norte), longitude=slice(oeste, este))
                
            # 2. Agregación espacial: Calculamos la media de todos los píxeles dentro de la caja
            ds_medio = ds_recortado.mean(dim=["latitude", "longitude"])
            
            # 3. Conversión a tabla plana de Pandas (Conserva tp, t2m o lo que venga dentro)
            df = ds_medio.to_dataframe().reset_index()
            
            # 4. Armonización cronológica de la cabecera temporal
            col_tiempo = next((c for c in ['time', 'valid_time', 'timestamp'] if c in df.columns), None)
            if col_tiempo:
                df.rename(columns={col_tiempo: 'fecha_hora'}, inplace=True)
            
            # 5. Selección inteligente: Nos quedamos con el tiempo y CUALQUIER variable analítica que traiga el NetCDF
            columnas_a_conservar = ['fecha_hora']
            for col in df.columns:
                if col not in ['fecha_hora', 'latitude', 'longitude', 'spatial_ref', 'crs']:
                    columnas_a_conservar.append(col)
            
            df_limpio = df[columnas_a_conservar].copy()
            
            # Aseguramos el orden cronológico
            df_limpio = df_limpio.sort_values('fecha_hora').reset_index(drop=True)
            return df_limpio
            
    except Exception as e:
        print(f"❌ Error crítico en el procesamiento del NetCDF: {e}")
        return None
    
# =====================================================================
# UTILIDAD 4: GENERACIÓN DE TOKEN PARA EUSKALMET
# =====================================================================
def generar_jwt_euskalmet(private_key_str, email_usuario):
    """
    Genera un JSON Web Token (JWT) dinámico firmado asimétricamente con RS256
    formateando la clave cruda al estándar PEM/PKCS#8 exigido por cryptography.
    """
    from datetime import datetime, timezone, timedelta
    
    ahora = datetime.now(timezone.utc)
    expiracion = ahora + timedelta(minutes=10) 
    
    payload = {
        "iss": "met01.apikey",  
        "iat": int(ahora.timestamp()),
        "exp": int(expiracion.timestamp()),
        "email": email_usuario
    }
    
    try:
        # 1. Limpieza absoluta de la clave cruda
        raw_key = private_key_str.replace("-----BEGIN RSA PRIVATE KEY-----", "")\
                                 .replace("-----END RSA PRIVATE KEY-----", "")\
                                 .replace("-----BEGIN PRIVATE KEY-----", "")\
                                 .replace("-----END PRIVATE KEY-----", "")\
                                 .replace("\n", "").replace("\r", "").strip()
        
        # 2. Troceamos la clave en bloques de 64 caracteres (Requisito estricto del formato PEM)
        lines = [raw_key[i:i+64] for i in range(0, len(raw_key), 64)]
        key_body = "\n".join(lines)
        
        # 3. Reconstruimos el certificado con la cabecera genérica PKCS#8
        key_formatted = f"-----BEGIN PRIVATE KEY-----\n{key_body}\n-----END PRIVATE KEY-----\n"

        # 4. Firmamos asimétricamente usando el algoritmo RS256 exigido
        token_firmado = jwt.encode(payload, key_formatted, algorithm="RS256")
        return token_firmado
    except Exception as e:
        print(f"❌ Error crítico en el motor criptográfico RS256: {e}")
        return None
    
    
# =====================================================================
# UTILIDAD 5: PARSEADOR CLI QUE ACEPTA CUENCA Y NIVEL
# =====================================================================    
def obtener_argumentos_cuenca_y_nivel():
    """
    Extensión del parseador CLI oficial para el entorno de producción/inferencia.
    Permite capturar dinámicamente tanto la cuenca como el nivel en tiempo real
    sin romper la lógica del diccionario centralizado ni del archivo .env.
    """
    parser = argparse.ArgumentParser(
        description="Core Orquestador - Entorno de Inferencia y Explotación en Tiempo Real."
    )
    
    opciones_validas = list(CONFIGURACION_CUENCAS.keys())
    
    parser.add_argument(
        "--cuenca",
        type=str,
        required=True,
        choices=opciones_validas,
        help="Clave identificadora de la cuenca hidrográfica a procesar."
    )
    
    # Registramos oficialmente el nuevo parámetro requerido para producción
    parser.add_argument(
        "--nivel",
        type=float,
        required=True,
        help="Lectura instantánea de nivel reportada por el sensor Edge (m)."
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    
    credenciales = {
        "AEMET": os.getenv("AEMET_API_KEY"),
        "EUSKALMET": os.getenv("EUSKALMET_API_KEY"),
        "SAI_API_KEY": os.getenv("SAI_API_KEY_CANTABRICO")
    }
    
    # Retorna el string identificador, los parámetros de la cuenca, las credenciales Y el nivel
    return args.cuenca, CONFIGURACION_CUENCAS[args.cuenca], credenciales, args.nivel