"""Lambda de inferencia · modelo base V1 (XGBoost por horizonte).

Comportamiento self-bootstrapping:
  - Si en s3://{bucket}/models/{cuenca}/current/ hay artefactos, los carga.
  - Si NO los hay, entrena un modelo XGBoost por horizonte usando la
    matriz de features de `gold/{cuenca}/matriz_features.parquet`, los
    sube a `models/{cuenca}/current/` y prosigue con la inferencia.

V1 deliberadamente sencillo: solo regresor XGBoost por horizonte
(t+1, t+2, t+4). La rama BiLSTM se aplaza a V2, cuando el dataset
acumule suficiente histórico para entrenar redes recurrentes en
SageMaker Studio Lab.

Endpoints aceptados (vía Lambda Function URL):
  - Cualquier GET o POST con payload vacío → predice usando la última fila
    disponible en gold y devuelve los 3 horizontes.
  - POST con `{"action": "retrain"}` → fuerza un reentrenamiento aunque
    ya exista modelo.

Variables de entorno:
  - BUCKET_NAME       — bucket del Data Lake
  - CUENCA            — identificador de la cuenca (por defecto urumea)
"""
import io
import json
import os
import tempfile

import boto3
import numpy as np
import pandas as pd
import xgboost as xgb

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")

HORIZONTES = [1, 2, 4]
MODELS_PREFIX = f"models/{CUENCA}/current"
MATRIX_KEY = f"gold/{CUENCA}/matriz_features.parquet"

# Cache en memoria entre invocaciones (Lambda reutiliza el contenedor)
_models: dict[int, xgb.Booster] | None = None
_feature_cols: list[str] | None = None


# ---------------------------------------------------------------------
# Helpers de I/O contra S3
# ---------------------------------------------------------------------
def _s3_get(key: str) -> bytes:
    return S3.get_object(Bucket=BUCKET, Key=key)["Body"].read()


def _s3_put(key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
    S3.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType=content_type)


def _s3_exists(key: str) -> bool:
    try:
        S3.head_object(Bucket=BUCKET, Key=key)
        return True
    except S3.exceptions.ClientError:
        return False


def _read_gold() -> pd.DataFrame:
    """Lee la matriz de features desde gold/ en un DataFrame."""
    tmp_path = "/tmp/matrix.parquet"
    with open(tmp_path, "wb") as f:
        f.write(_s3_get(MATRIX_KEY))
    return pd.read_parquet(tmp_path, engine="fastparquet")


# ---------------------------------------------------------------------
# Entrenamiento del modelo base
# ---------------------------------------------------------------------
def _entrenar_y_guardar() -> dict[int, xgb.Booster]:
    """Entrena un XGBoost por horizonte y persiste los artefactos en S3."""
    print(f"🏋️  Entrenando modelo base desde {MATRIX_KEY}")
    df = _read_gold()

    target_cols = [c for c in df.columns if c.startswith("TARGET_")]
    if not target_cols:
        raise RuntimeError("La matriz gold no contiene columnas TARGET_*")

    feature_cols = [c for c in df.columns if c not in target_cols and c != "fecha_hora"]
    X = df[feature_cols].values.astype(np.float32)

    modelos: dict[int, xgb.Booster] = {}

    for h in HORIZONTES:
        target_col = next((c for c in target_cols if c.endswith(f"_t+{h}")), None)
        if target_col is None:
            print(f"   ⚠️ No hay TARGET para horizonte t+{h}, saltando")
            continue

        y = df[target_col].values.astype(np.float32)
        dtrain = xgb.DMatrix(X, label=y, feature_names=feature_cols)

        params = {
            "objective": "reg:squarederror",
            "max_depth": 3,
            "eta": 0.1,
            "verbosity": 0,
        }
        booster = xgb.train(params, dtrain, num_boost_round=50)
        modelos[h] = booster

        # Persistir el modelo en S3 (formato JSON nativo de XGBoost)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            booster.save_model(tmp.name)
            tmp.flush()
            with open(tmp.name, "rb") as f:
                _s3_put(f"{MODELS_PREFIX}/xgb_t+{h}.json", f.read(), "application/json")
        os.unlink(tmp.name)
        print(f"   ✓ XGB t+{h} entrenado y subido")

    # Persistir las columnas de features usadas (para garantizar el orden en inferencia)
    _s3_put(
        f"{MODELS_PREFIX}/feature_cols.json",
        json.dumps(feature_cols).encode("utf-8"),
        "application/json",
    )
    print(f"✅ Modelo base persistido en s3://{BUCKET}/{MODELS_PREFIX}/")

    return modelos


def _cargar_modelos() -> tuple[dict[int, xgb.Booster], list[str]]:
    """Carga los modelos desde S3 si existen; si no, entrena y devuelve los recién creados."""
    feature_cols_key = f"{MODELS_PREFIX}/feature_cols.json"

    if not _s3_exists(feature_cols_key):
        print("📭 No hay modelo previo en S3, entrenando uno base…")
        modelos = _entrenar_y_guardar()
        feature_cols = json.loads(_s3_get(feature_cols_key).decode("utf-8"))
        return modelos, feature_cols

    print("📦 Cargando modelos preexistentes desde S3")
    feature_cols = json.loads(_s3_get(feature_cols_key).decode("utf-8"))
    modelos: dict[int, xgb.Booster] = {}
    for h in HORIZONTES:
        key = f"{MODELS_PREFIX}/xgb_t+{h}.json"
        if not _s3_exists(key):
            continue
        local = f"/tmp/xgb_t+{h}.json"
        with open(local, "wb") as f:
            f.write(_s3_get(key))
        booster = xgb.Booster()
        booster.load_model(local)
        modelos[h] = booster
    print(f"✅ Cargados {len(modelos)} modelos (horizontes {list(modelos.keys())})")
    return modelos, feature_cols


# ---------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------
def lambda_handler(event, context):
    global _models, _feature_cols

    # Detectar si se pide reentrenamiento explícito
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except Exception:  # noqa: BLE001
            body = {}
    forzar_retrain = body.get("action") == "retrain"

    if forzar_retrain or _models is None:
        if forzar_retrain:
            print("🔄 Reentrenamiento solicitado vía payload")
            _models = _entrenar_y_guardar()
            _feature_cols = json.loads(_s3_get(f"{MODELS_PREFIX}/feature_cols.json").decode("utf-8"))
        else:
            _models, _feature_cols = _cargar_modelos()

    # Leer la última fila de la matriz para predecir
    df = _read_gold()
    if df.empty:
        return _resp(400, {"error": "La matriz de features está vacía"})

    ultima = df.iloc[[-1]][_feature_cols].values.astype(np.float32)
    dpredict = xgb.DMatrix(ultima, feature_names=_feature_cols)

    predicciones = {
        f"t+{h}": float(round(_models[h].predict(dpredict)[0], 4))
        for h in HORIZONTES
        if h in _models
    }

    return _resp(
        200,
        {
            "cuenca": CUENCA,
            "timestamp_input": str(df["fecha_hora"].iloc[-1]),
            "variable_target": "precipitacion_mm",
            "predicciones": predicciones,
            "modelo": "xgboost_v1_base",
            "n_horizontes": len(predicciones),
        },
    )


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
