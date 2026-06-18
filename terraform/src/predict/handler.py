"""Endpoint de inferencia del ensemble BiLSTM + XGBoost.

Carga los artefactos del modelo desde `s3://{bucket}/models/{cuenca}/current/`
(que apunta a la última versión publicada desde SageMaker Studio Lab) y
devuelve la predicción de nivel para los cinco horizontes definidos
en el TFM: t+1, t+4, t+8, t+12, t+24.

Invocación:
    GET / POST a la Function URL pública. Sin payload: usa los últimos
    datos disponibles en gold/{cuenca}/matriz_features.parquet.
"""
import io
import json
import os

import boto3
import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
import xgboost as xgb

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")

HORIZONTES = [1, 4, 8, 12, 24]
VENTANA_BILSTM = 24  # filas hacia atrás que necesita la BiLSTM

# Caches en memoria entre invocaciones (Lambda reutiliza el contenedor)
_xgb_models: dict[int, xgb.Booster] | None = None
_bilstm_model: tf.keras.Model | None = None
_scaler = None


def _s3_get(key: str) -> bytes:
    return S3.get_object(Bucket=BUCKET, Key=key)["Body"].read()


def _cargar_artefactos():
    """Lazy-load de los artefactos. Solo se ejecuta en el primer invoke."""
    global _xgb_models, _bilstm_model, _scaler
    if _xgb_models is not None:
        return

    prefix = f"models/{CUENCA}/current"
    print(f"🔄 Cargando artefactos desde s3://{BUCKET}/{prefix}/")

    # XGBoost: un .json por horizonte (saved con booster.save_model("h1.json"))
    _xgb_models = {}
    for h in HORIZONTES:
        local = f"/tmp/xgb_t+{h}.json"
        with open(local, "wb") as f:
            f.write(_s3_get(f"{prefix}/xgb_t+{h}.json"))
        booster = xgb.Booster()
        booster.load_model(local)
        _xgb_models[h] = booster

    # BiLSTM: un único .keras
    local_bilstm = "/tmp/bilstm.keras"
    with open(local_bilstm, "wb") as f:
        f.write(_s3_get(f"{prefix}/bilstm.keras"))
    _bilstm_model = tf.keras.models.load_model(local_bilstm, compile=False)

    # Scaler (StandardScaler de sklearn, persistido con joblib)
    with io.BytesIO(_s3_get(f"{prefix}/scaler.joblib")) as buf:
        _scaler = joblib.load(buf)

    print("✅ Artefactos cargados en memoria")


def _ultima_ventana() -> pd.DataFrame:
    """Lee la matriz gold y devuelve las últimas filas necesarias."""
    raw = _s3_get(f"gold/{CUENCA}/matriz_features.parquet")
    df = pd.read_parquet(io.BytesIO(raw))
    return df.tail(VENTANA_BILSTM)


def _preparar_features(df: pd.DataFrame):
    """Selecciona las columnas de features, las escala y devuelve 2D + 3D."""
    target_cols = [c for c in df.columns if c.startswith("TARGET_t+")]
    feature_cols = [c for c in df.columns if c not in target_cols and c != "fecha_hora"]
    X = df[feature_cols].values
    X_scaled = _scaler.transform(X)
    X_3d = X_scaled.reshape(1, X_scaled.shape[0], X_scaled.shape[1])
    return X_scaled, X_3d, feature_cols


def lambda_handler(event, context):
    _cargar_artefactos()

    df = _ultima_ventana()
    if len(df) < VENTANA_BILSTM:
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": f"Sin histórico suficiente ({len(df)}/{VENTANA_BILSTM} filas)"}
            ),
        }

    X_scaled, X_3d, _ = _preparar_features(df)

    # XGBoost: usa la última fila escalada
    dlast = xgb.DMatrix(X_scaled[-1:])
    preds_xgb = {h: float(_xgb_models[h].predict(dlast)[0]) for h in HORIZONTES}

    # BiLSTM: salida vectorial (1, len(HORIZONTES))
    preds_bilstm_raw = _bilstm_model.predict(X_3d, verbose=0)[0]
    preds_bilstm = {h: float(preds_bilstm_raw[i]) for i, h in enumerate(HORIZONTES)}

    # Ensemble simple: media. El TFM puede argumentar pesos según validación.
    preds_ensemble = {
        h: round((preds_xgb[h] + preds_bilstm[h]) / 2.0, 4) for h in HORIZONTES
    }

    body = {
        "cuenca": CUENCA,
        "timestamp_input": str(df["fecha_hora"].iloc[-1]),
        "predicciones_nivel_m": preds_ensemble,
        "detalle": {
            "xgboost": {f"t+{h}": round(preds_xgb[h], 4) for h in HORIZONTES},
            "bilstm":  {f"t+{h}": round(preds_bilstm[h], 4) for h in HORIZONTES},
        },
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
