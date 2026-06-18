"""Ingesta horaria de telemetría hidrológica desde Euskalmet (cuenca del Urumea).

Euskalmet exige autenticación JWT firmado con RS256. La clave privada PEM y
el email registrado en Open Data Euskadi se almacenan en SSM Parameter Store.

El resultado se escribe como CSV en la zona bronze del Data Lake bajo:

    bronze/hidro/{cuenca}/{YYYY}/{MM}/{DD}/{HH}/lectura.csv
"""
import os
import time
from datetime import datetime, timedelta, timezone

import boto3
import jwt
import pandas as pd
import requests

S3 = boto3.client("s3")
SSM = boto3.client("ssm")

BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")
ESTACION = os.environ["EUSKALMET_ESTACION"]
SENSOR_ID = os.environ["EUSKALMET_SENSOR_ID"]
MEASURE_TYPE = os.environ["EUSKALMET_MEASURE_TYPE"]
MEASURE_ID = os.environ["EUSKALMET_MEASURE_ID"]
PRIVKEY_PARAM = os.environ["EUSKALMET_PRIVKEY_PARAM"]
EMAIL_PARAM = os.environ["EUSKALMET_EMAIL_PARAM"]


def _ssm(name, decrypt=True):
    return SSM.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]


def _generar_jwt(privkey_pem: str, email: str) -> str:
    """Firma un JWT RS256 con la clave privada de Euskalmet, válido 5 min."""
    ahora = int(time.time())
    payload = {
        "iss": email,
        "iat": ahora,
        "exp": ahora + 60 * 5,
    }
    return jwt.encode(payload, privkey_pem, algorithm="RS256")


def lambda_handler(event, context):
    privkey = _ssm(PRIVKEY_PARAM, decrypt=True)
    email = _ssm(EMAIL_PARAM, decrypt=False)
    token = _generar_jwt(privkey, email)

    # Margen de 15 min hacia atrás para asegurar que la lectura está indexada
    ahora = datetime.now(timezone.utc) - timedelta(minutes=15)
    yyyy, mm, dd, hh = (
        f"{ahora.year}",
        f"{ahora.month:02d}",
        f"{ahora.day:02d}",
        f"{ahora.hour:02d}",
    )

    url = (
        "https://api.euskadi.eus/euskalmet/readings/forStation/"
        f"{ESTACION}/{SENSOR_ID}/measures/{MEASURE_TYPE}/{MEASURE_ID}/"
        f"at/{yyyy}/{mm}/{dd}/{hh}"
    )

    print(f"📡 GET Euskalmet · {url}")
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    datos = response.json()

    # Estructura: a veces lista (medidas minutarias), a veces dict (puntual)
    if isinstance(datos, list) and datos:
        lectura = datos[-1]
    elif isinstance(datos, dict):
        lectura = datos
    else:
        raise ValueError(f"Estructura JSON Euskalmet desconocida: {type(datos)}")

    caudal = float(lectura.get("value", 0))
    fecha = lectura.get("date", ahora.strftime("%Y-%m-%d %H:%M:%S"))

    df = pd.DataFrame([{"fecha_hora": pd.to_datetime(fecha), "caudal_m3s": caudal}])

    key = f"bronze/hidro/{CUENCA}/{ahora:%Y/%m/%d/%H}/lectura.csv"
    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )

    print(f"✅ caudal {caudal} m³/s registrado en s3://{BUCKET}/{key}")
    return {"status": "ok", "caudal_m3s": caudal, "s3_key": key}
