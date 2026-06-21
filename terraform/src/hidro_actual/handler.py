"""Ingesta horaria Euskalmet (Ereñozu C0F0, cuenca Urumea).

Adaptación literal de `hidro_actual.py::descargar_telemetria_rio` (rama
api_tipo == "euskalmet") y de `utils_adquisicion_datos.py::generar_jwt_euskalmet`.

Ajustes mínimos para entorno Lambda:
  - Credenciales desde SSM Parameter Store en lugar de .env / load_dotenv.
  - Persistencia en S3 en lugar de CSV local.
"""
import os
from datetime import datetime, timezone, timedelta

import boto3
import jwt  # type: ignore
import pandas as pd
import requests

S3 = boto3.client("s3")
SSM = boto3.client("ssm")

BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")
ESTACION_ID = os.environ.get("EUSKALMET_ESTACION", "C0F0")
SENSOR_ID = os.environ.get("EUSKALMET_SENSOR_ID", "CAF0")
MEASURE_TYPE = os.environ.get("EUSKALMET_MEASURE_TYPE", "measuresForWater")
MEASURE_ID = os.environ.get("EUSKALMET_MEASURE_ID", "flow_1")
PRIVKEY_PARAM = os.environ["EUSKALMET_PRIVKEY_PARAM"]
EMAIL_PARAM = os.environ["EUSKALMET_EMAIL_PARAM"]


# === COPIA LITERAL DE utils_adquisicion_datos.py::generar_jwt_euskalmet =====
def generar_jwt_euskalmet(private_key_str, email_usuario):
    """
    Genera un JSON Web Token (JWT) dinámico firmado asimétricamente con RS256
    formateando la clave cruda al estándar PEM/PKCS#8 exigido por cryptography.
    """
    ahora = datetime.now(timezone.utc)
    expiracion = ahora + timedelta(minutes=10)

    payload = {
        "iss": "met01.apikey",
        "iat": int(ahora.timestamp()),
        "exp": int(expiracion.timestamp()),
        "email": email_usuario,
    }

    # 1. Limpieza absoluta de la clave cruda
    raw_key = (
        private_key_str
        .replace("-----BEGIN RSA PRIVATE KEY-----", "")
        .replace("-----END RSA PRIVATE KEY-----", "")
        .replace("-----BEGIN PRIVATE KEY-----", "")
        .replace("-----END PRIVATE KEY-----", "")
        .replace("\n", "")
        .replace("\r", "")
        .strip()
    )

    # 2. Troceamos la clave en bloques de 64 caracteres (formato PEM estricto)
    lines = [raw_key[i:i + 64] for i in range(0, len(raw_key), 64)]
    key_body = "\n".join(lines)

    # 3. Reconstruimos con la cabecera genérica PKCS#8
    key_formatted = f"-----BEGIN PRIVATE KEY-----\n{key_body}\n-----END PRIVATE KEY-----\n"

    # 4. Firmamos con RS256
    return jwt.encode(payload, key_formatted, algorithm="RS256")
# ============================================================================


def lambda_handler(event, context):
    # Credenciales desde SSM (sustituye a load_dotenv de Daniel)
    private_key = SSM.get_parameter(Name=PRIVKEY_PARAM, WithDecryption=True)["Parameter"]["Value"]
    email_registrado = SSM.get_parameter(Name=EMAIL_PARAM)["Parameter"]["Value"]

    print("🔐 Generando firma asimétrica RS256 (Daniel-style)…")
    token = generar_jwt_euskalmet(private_key, email_registrado)

    # === LITERAL hidro_actual.py:15-37 ====================================
    ahora_utc = datetime.now(timezone.utc)
    tiempo_seguro = ahora_utc - timedelta(minutes=15)  # colchón de 15 min

    yyyy = str(tiempo_seguro.year)
    mm = f"{tiempo_seguro.month:02d}"
    dd = f"{tiempo_seguro.day:02d}"
    hh = f"{tiempo_seguro.hour:02d}"

    url = (
        f"https://api.euskadi.eus/euskalmet/readings/forStation/"
        f"{ESTACION_ID}/{SENSOR_ID}/measures/{MEASURE_TYPE}/{MEASURE_ID}/"
        f"at/{yyyy}/{mm}/{dd}/{hh}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    print(f"🚀 GET {url}")
    # ======================================================================

    # Petición con reintentos (equivalente a hacer_peticion_robusta)
    res = None
    for intento in range(1, 4):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            res = r
            break
        except requests.RequestException as exc:
            print(f"   ⚠️ Intento {intento}/3 falló: {exc}")
            if intento < 3:
                import time
                time.sleep(5)

    if res is None:
        print("   -> Contingencia de Daniel: caudal base histórico 14.8 m3/s")
        df = pd.DataFrame([{"fecha_hora": pd.Timestamp.now().floor("h"), "caudal_m3s": 14.8}])
    else:
        # === LITERAL hidro_actual.py:59-69 ================================
        datos = res.json()
        if isinstance(datos, list) and len(datos) > 0:
            lectura = datos[-1]
            caudal = float(lectura.get("value", 12.5))
            fecha_str = lectura.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        elif isinstance(datos, dict):
            caudal = float(datos.get("value", 12.5))
            fecha_str = datos.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            raise ValueError("Estructura de payload JSON desconocida")
        # ====================================================================

        df = pd.DataFrame([{"fecha_hora": pd.to_datetime(fecha_str), "caudal_m3s": caudal}])
        print(f"   ✅ Ereñozu ({MEASURE_ID}) = {caudal} m3/s @ {fecha_str}")

    key = f"bronze/hidro/{CUENCA}/{ahora_utc:%Y/%m/%d/%H}/lectura.csv"
    S3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )
    print(f"💾 s3://{BUCKET}/{key}")
    return {"status": "ok", "rows": int(len(df)), "s3_key": key}
