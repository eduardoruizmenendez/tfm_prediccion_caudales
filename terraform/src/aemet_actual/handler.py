"""Ingesta horaria de observaciones convencionales AEMET (estación 1024E).

La API de AEMET sigue un patrón de doble paso:
  1. Petición autenticada que devuelve una URL temporal.
  2. Descarga de los datos JSON desde esa URL temporal.

Decisiones de seguridad:
  - La api_key se envía en CABECERA HTTP, no en query string, para que
    los mensajes de error de `requests` no la incluyan en los logs.
  - Si ocurre cualquier excepción HTTP, se sanea el mensaje antes de
    re-lanzar la excepción.

Resultado: bronze/aemet_actual/{cuenca}/{YYYY}/{MM}/{DD}/{HH}/observaciones.csv
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
ESTACION = os.environ.get("AEMET_ESTACION", "1024E")
SSM_PARAM = os.environ["AEMET_SSM_PARAM"]

MAX_REINTENTOS = 3
ESPERA_429 = 15  # segundos a esperar tras un 429 antes de reintentar


def _api_key() -> str:
    response = SSM.get_parameter(Name=SSM_PARAM, WithDecryption=True)
    return response["Parameter"]["Value"]


def _peticion_aemet(url: str, api_key: str, etapa: str) -> dict:
    """Petición robusta con reintentos exponenciales y mensajes de error sin secretos."""
    headers = {
        "cache-control": "no-cache",
        "api_key": api_key,  # AEMET admite api_key en cabecera, no expuesto en URLs
    }
    last_status = None

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()
            last_status = r.status_code
            if r.status_code == 429:
                # AEMET rate-limit: esperar y reintentar
                print(f"   ⚠️ [{etapa}] 429 Too Many Requests — esperando {ESPERA_429}s antes de reintentar")
                time.sleep(ESPERA_429 * intento)  # backoff lineal
                continue
            # Otros códigos de error: log sin url y re-lanzar limpio
            raise RuntimeError(f"AEMET {etapa} devolvió status {r.status_code}")
        except requests.RequestException as exc:
            print(f"   ⚠️ [{etapa}] error de red (intento {intento}/{MAX_REINTENTOS}): {type(exc).__name__}")
            time.sleep(5 * intento)

    raise RuntimeError(f"AEMET {etapa} agotó {MAX_REINTENTOS} reintentos (último status: {last_status})")


def lambda_handler(event, context):
    api_key = _api_key()

    # Paso 1 — petición indirecta
    url_indice = f"https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/{ESTACION}"
    print(f"📡 AEMET paso 1: {url_indice}")
    indice = _peticion_aemet(url_indice, api_key, etapa="paso1")

    if indice.get("estado") != 200:
        raise RuntimeError(f"AEMET respondió estado {indice.get('estado')}: {indice.get('descripcion')}")

    # Paso 2 — descarga real desde la URL temporal (sin la api_key, esa URL es ya autenticada)
    url_datos = indice["datos"]
    print(f"📡 AEMET paso 2: descargando JSON de datos…")
    r2 = requests.get(url_datos, timeout=30)
    if r2.status_code != 200:
        raise RuntimeError(f"AEMET paso2 devolvió status {r2.status_code}")

    df = pd.DataFrame(r2.json())
    if "fint" in df.columns:
        df["fecha_hora"] = pd.to_datetime(df["fint"])

    ahora = datetime.now(timezone.utc)
    key = f"bronze/aemet_actual/{CUENCA}/{ahora:%Y/%m/%d/%H}/observaciones.csv"
    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )

    print(f"✅ {len(df)} filas escritas en s3://{BUCKET}/{key}")
    return {"status": "ok", "rows": int(len(df)), "s3_key": key}
