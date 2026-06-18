"""Generación de la matriz de características (versión AEMET-only para V1).

Para validar el pipeline end-to-end con una sola fuente, esta Lambda
lee únicamente los CSV acumulados de AEMET en la zona bronce y
construye una matriz simplificada en la zona gold:

    gold/{cuenca}/matriz_features.parquet

Las variables derivadas son las descritas en el TFM, adaptadas a lo
que AEMET expone en la estación 1024E (San Sebastián / Igueldo):

  · Temperatura del aire (ta)        — variable continua
  · Precipitación (prec)             — variable continua, target candidato
  · Humedad relativa (hr)            — variable continua
  · Lags de temperatura a 1, 4, 8, 12 y 24 horas
  · Ventanas móviles de precipitación a 12 y 24 horas
  · Codificación cíclica del mes (seno/coseno)
  · TARGETs: precipitación desplazada t+1, t+4, t+8, t+12, t+24

Cuando se sumen las otras fuentes (Open-Meteo y Euskalmet) se
reincorporarán la precipitación media areal y el nivel del río como
variables principales.
"""
import io
import os

import boto3
import numpy as np
import pandas as pd

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")

# V1 con AEMET-only: lags y horizontes recortados para que el pipeline
# devuelva filas útiles con apenas 12 h de histórico (lo que entrega AEMET
# en una llamada). Cuando se sumen Open-Meteo y Euskalmet se restablecerá
# la ventana completa [1, 4, 8, 12, 24] del apartado 4.3.4 del TFM.
HORIZONTES = [1, 2, 4]
LAGS = [1, 2, 4]


def _list_csvs(prefix: str):
    paginator = S3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                yield obj["Key"]


def _read_csv(key: str) -> pd.DataFrame:
    obj = S3.get_object(Bucket=BUCKET, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def _write_parquet(df: pd.DataFrame, key: str) -> None:
    # fastparquet cierra el BytesIO al terminar de escribir, así que
    # pasamos por un fichero en /tmp (Lambda ofrece 512 MB de /tmp por defecto)
    tmp_path = "/tmp/matriz.parquet"
    df.to_parquet(tmp_path, index=False, engine="fastparquet")
    with open(tmp_path, "rb") as f:
        S3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=f.read(),
            ContentType="application/octet-stream",
        )


def lambda_handler(event, context):
    print(f"🔧 Generando matriz AEMET-only para cuenca='{CUENCA}'")

    prefix = f"bronze/aemet_actual/{CUENCA}/"
    chunks = []
    for key in _list_csvs(prefix):
        try:
            chunks.append(_read_csv(key))
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  Saltando {key}: {exc}")

    if not chunks:
        print("Sin datos de AEMET acumulados todavía.")
        return {"status": "no-data"}

    df = pd.concat(chunks, ignore_index=True)
    print(f"  · Filas crudas leídas: {len(df)}")

    # Asegurar columna temporal y orden cronológico
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    df = (
        df.dropna(subset=["fecha_hora"])
        .drop_duplicates(subset=["fecha_hora"])
        .sort_values("fecha_hora")
        .reset_index(drop=True)
    )
    print(f"  · Filas únicas tras dedup: {len(df)}")

    # Conservar solo las columnas relevantes (las que AEMET trae)
    columnas_interes = ["fecha_hora", "ta", "prec", "hr"]
    df = df[[c for c in columnas_interes if c in df.columns]].copy()

    # Lags de temperatura
    if "ta" in df.columns:
        for lag in LAGS:
            df[f"ta_t-{lag}"] = df["ta"].shift(lag)

    # Ventanas móviles de precipitación (V1: 2h y 4h, V2 ampliará a 12h y 24h)
    if "prec" in df.columns:
        df["prec_2h"] = df["prec"].rolling(2, min_periods=1).sum()
        df["prec_4h"] = df["prec"].rolling(4, min_periods=1).sum()

    # Codificación cíclica del mes
    mes = df["fecha_hora"].dt.month
    df["mes_sin"] = np.sin(2 * np.pi * mes / 12)
    df["mes_cos"] = np.cos(2 * np.pi * mes / 12)

    # Targets multi-horizonte sobre precipitación
    if "prec" in df.columns:
        for h in HORIZONTES:
            df[f"TARGET_prec_t+{h}"] = df["prec"].shift(-h)

    df = df.dropna().reset_index(drop=True)
    if df.empty:
        return {"status": "insufficient-history", "rows": 0}

    key = f"gold/{CUENCA}/matriz_features.parquet"
    _write_parquet(df, key)

    print(f"✅ {len(df)} filas escritas en s3://{BUCKET}/{key}")
    return {
        "status": "ok",
        "rows": int(len(df)),
        "cols": len(df.columns),
        "s3_key": key,
    }
