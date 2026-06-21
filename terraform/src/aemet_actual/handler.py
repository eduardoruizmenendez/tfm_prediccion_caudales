"""Ingesta horaria AEMET (observación convencional, cuenca Urumea).

Adaptación literal de `aemet_actual.py::descargar_aemet_horario`
+ `utils_adquisicion_datos.py::hacer_peticion_robusta`.

Ajustes mínimos para entorno Lambda:
  - api_key desde SSM Parameter Store en lugar de .env / load_dotenv.
  - Persistencia en S3 en lugar de CSV local.
"""
import os
import time
from datetime import datetime, timezone

import boto3
import pandas as pd
import requests

S3 = boto3.client("s3")
SSM = boto3.client("ssm")

BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")
ESTACION = os.environ.get("AEMET_ESTACION", "1024E")  # Igueldo (Urumea), tal cual Daniel
SSM_PARAM = os.environ["AEMET_SSM_PARAM"]


# === COPIA LITERAL de utils_adquisicion_datos.py::hacer_peticion_robusta ===
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
# ===========================================================================


def descargar_aemet_horario(api_key, id_estacion):
    """Adaptado de aemet_actual.py:9-83 — escribe a S3 en vez de CSV local."""
    print(f"📡 Conectando con AEMET (Tiempo Real) para la estación {id_estacion}...")

    url_peticion = f"https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/{id_estacion}"
    querystring = {"api_key": api_key}
    headers = {"cache-control": "no-cache"}

    # PASO 1
    res_1 = hacer_peticion_robusta(url_peticion, headers=headers, params=querystring)
    if res_1 is None:
        return None

    datos_res_1 = res_1.json()

    if datos_res_1.get("estado") == 200:
        url_datos = datos_res_1.get("datos")
        print("✅ Permiso concedido. Descargando datos horarios consolidados...")

        # PASO 2
        res_2 = hacer_peticion_robusta(url_datos)
        if res_2 is None:
            return None

        datos_reales = res_2.json()
        df = pd.DataFrame(datos_reales)

        if "fint" in df.columns:
            df["fecha_hora"] = pd.to_datetime(df["fint"])

            columnas_deseadas = ["fecha_hora"]
            if "prec" in df.columns:
                columnas_deseadas.append("prec")
            if "ta" in df.columns:
                columnas_deseadas.append("ta")

            df_limpio = df[columnas_deseadas].copy()
            df_limpio = df_limpio.sort_values("fecha_hora").reset_index(drop=True)

            if "prec" in df_limpio.columns:
                df_limpio["prec"] = df_limpio["prec"].fillna(0.0)

            return df_limpio
        else:
            print("⚠️ No se encontró la columna 'fint' en la respuesta de AEMET.")
            return df

    elif datos_res_1.get("estado") == 404 or "No hay datos" in datos_res_1.get("descripcion", ""):
        print("   ⚠️ Estación temporalmente desconectada. Insertando dummy row.")
        hora_actual = pd.Timestamp.now().floor("h")
        return pd.DataFrame([{"fecha_hora": hora_actual, "prec": 0.0, "ta": None}])

    else:
        print(f"❌ Error AEMET: {datos_res_1.get('descripcion')}")
        return None


def lambda_handler(event, context):
    api_key = SSM.get_parameter(Name=SSM_PARAM, WithDecryption=True)["Parameter"]["Value"]

    df = descargar_aemet_horario(api_key, ESTACION)
    if df is None:
        raise RuntimeError("AEMET no devolvió datos ni dummy row tras reintentos")

    ahora = datetime.now(timezone.utc)
    key = f"bronze/aemet_actual/{CUENCA}/{ahora:%Y/%m/%d/%H}/observaciones.csv"
    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )
    print(f"💾 s3://{BUCKET}/{key} ({len(df)} filas)")
    return {"status": "ok", "rows": int(len(df)), "s3_key": key}
