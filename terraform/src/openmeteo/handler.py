"""Ingesta horaria de pronóstico Open-Meteo (cuenca del Urumea, V1).

Recupera la previsión de precipitación a 72 h en tres puntos a lo largo del
cauce y calcula el promedio areal. El resultado se escribe como CSV en la
zona bronze del Data Lake bajo la clave:

    bronze/openmeteo/{cuenca}/{YYYY}/{MM}/{DD}/{HH}/forecast.csv
"""
import os
from datetime import datetime, timezone

import boto3
import pandas as pd
import requests

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")

# Configuración del Urumea (V1 hardcodeado).
# Para V2 multi-cuenca este diccionario se moverá a SSM Parameter Store.
PUNTOS = {
    "Cabecera":      (43.15, -1.91),
    "Tramo_Medio":   (43.26, -1.97),
    "Desembocadura": (43.32, -1.98),
}
HORIZONTE_HORAS = 72


def lambda_handler(event, context):
    lats = ",".join(str(lat) for lat, _ in PUNTOS.values())
    lons = ",".join(str(lon) for _, lon in PUNTOS.values())
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        f"&hourly=precipitation&forecast_hours={HORIZONTE_HORAS}"
    )

    print(f"📡 GET Open-Meteo · {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()

    # Construcción del DataFrame multipunto (un payload por punto, en el mismo orden que PUNTOS)
    df_forecast = None
    for i, nombre in enumerate(PUNTOS):
        df_punto = pd.DataFrame(
            {
                "fecha_hora": pd.to_datetime(payload[i]["hourly"]["time"]),
                f"precip_mm_{nombre}": payload[i]["hourly"]["precipitation"],
            }
        )
        df_forecast = df_punto if df_forecast is None else df_forecast.merge(df_punto, on="fecha_hora")

    # Precipitación media areal de la cuenca
    cols_precip = [c for c in df_forecast.columns if c.startswith("precip_mm_")]
    df_forecast["precipitacion_media_cuenca_mm"] = df_forecast[cols_precip].mean(axis=1)

    # Persistencia en S3
    ahora = datetime.now(timezone.utc)
    key = f"bronze/openmeteo/{CUENCA}/{ahora:%Y/%m/%d/%H}/forecast.csv"
    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=df_forecast.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )

    print(f"✅ {len(df_forecast)} filas escritas en s3://{BUCKET}/{key}")
    return {"status": "ok", "rows": int(len(df_forecast)), "s3_key": key}
