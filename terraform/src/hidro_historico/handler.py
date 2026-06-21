"""Lambda one-shot: descarga histórico hidrológico del Urumea (Open Data Euskadi).

Adaptación literal de `descarga_hidro_h.py::descargar_historico_urumea`
(líneas 10-64). Sin JWT, sin Euskalmet: lee XML anuales públicos.

Itineración: 2020 → año actual.
Salida: bronze/hidro_hist/urumea/historico_completo.csv
Columnas: fecha_hora, caudal_m3s, nivel_m
"""
import io
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import boto3
import pandas as pd
import requests

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
ESTACION = os.environ.get("URUMEA_ESTACION", "C0F0")
DESTINO_KEY = "bronze/hidro_hist/urumea/historico_completo.csv"

URL_TEMPLATE = (
    "https://opendata.euskadi.eus/contenidos/ds_meteorologicos/"
    "met_stations_ds_{ano}/opendata/{ano}/{estacion}/{estacion}_{ano}_1.xml"
)


def lambda_handler(event, context):
    # === LITERAL descarga_hidro_h.py:17-64 ================================
    print(f"🛰️  Conectando con Open Data Euskadi (estación {ESTACION})...")

    ano_actual = datetime.now().year
    registros_totales = []

    for ano in range(2020, ano_actual + 1):
        url_xml = URL_TEMPLATE.format(ano=ano, estacion=ESTACION)
        print(f"   -> Descargando año {ano}...")
        try:
            res = requests.get(url_xml, timeout=60)
            if res.status_code != 200:
                print(f"      ⚠️ Archivo no disponible para {ano}. Saltando...")
                continue

            root = ET.fromstring(res.content)
            for dia_nodo in root.findall(".//dia"):
                fecha_base = dia_nodo.get("Dia")
                for hora_nodo in dia_nodo.findall(".//hora"):
                    hora_base = hora_nodo.get("Hora")
                    meteoros = hora_nodo.find(".//Meteoros")
                    if meteoros is not None:
                        caudal_nodo = meteoros.find("Caudal2._a_0cm")
                        nivel_nodo = meteoros.find("Nivel2._a_0cm")
                        caudal_val = float(caudal_nodo.text) if caudal_nodo is not None and caudal_nodo.text else None
                        nivel_val = float(nivel_nodo.text) if nivel_nodo is not None and nivel_nodo.text else None
                        if caudal_val is None and nivel_val is None:
                            continue
                        registros_totales.append({
                            "fecha_hora": f"{fecha_base} {hora_base}:00",
                            "caudal_m3s": caudal_val,
                            "nivel_m": nivel_val,
                        })
        except Exception as e:
            print(f"      ❌ Error procesando {ano}: {e}")
    # ========================================================================

    if not registros_totales:
        print("❌ No se extrajeron registros.")
        return {"status": "no-data", "rows": 0}

    df_historico = pd.DataFrame(registros_totales)
    df_historico["fecha_hora"] = pd.to_datetime(df_historico["fecha_hora"])
    df_horario = (
        df_historico
        .groupby(df_historico["fecha_hora"].dt.floor("h"))
        .mean(numeric_only=True)
        .reset_index()
        .sort_values("fecha_hora")
        .reset_index(drop=True)
    )

    csv_bytes = df_horario.to_csv(index=False).encode("utf-8")
    S3.put_object(Bucket=BUCKET, Key=DESTINO_KEY, Body=csv_bytes, ContentType="text/csv")

    print(f"🏆 {len(df_horario)} filas horarias escritas en s3://{BUCKET}/{DESTINO_KEY}")
    return {"status": "ok", "rows": int(len(df_horario)), "s3_key": DESTINO_KEY}
