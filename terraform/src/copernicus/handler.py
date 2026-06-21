"""Lambda one-shot: descarga ERA5-Land mensual de Copernicus y sube a bronze.

Adaptación literal de:
  - copernicus_masivo_lluvia_h.py::configurar_credenciales_cds (líneas 11-16)
  - copernicus_masivo_lluvia_h.py::descargar_mes_lluvia (líneas 21-96)
  - utils_adquisicion_datos.py::procesar_netcdf_a_dataframe (líneas 66-114)

Invocación (un mes por llamada):
  aws lambda invoke --function-name tfm-caudales-copernicus \
    --payload '{"year": 2020, "month": 1}' out.json

Salida: bronze/era5/{cuenca}/{year}/{month:02d}/lluvia_temp.csv
Columnas: fecha_hora, tp, t2m
"""
import os
import boto3

S3 = boto3.client("s3")
SSM = boto3.client("ssm")

BUCKET = os.environ["BUCKET_NAME"]
CUENCA = os.environ.get("CUENCA", "urumea")
CDS_SSM_PARAM = os.environ["CDS_API_KEY_PARAM"]

# Coordenadas Urumea de config_adquisicion_datos.py: [Norte, Oeste, Sur, Este]
COORDENADAS = [43.10, -2.05, 43.35, -1.75]
NC_TMP = "/tmp/temp_descarga.nc"


# === COPIA LITERAL utils_adquisicion_datos.py::procesar_netcdf_a_dataframe ===
def procesar_netcdf_a_dataframe(ruta_netcdf, coordenadas):
    import xarray as xr
    import pandas as pd

    print(f"📦 Abriendo y procesando NetCDF: {ruta_netcdf}")
    norte, oeste, sur, este = coordenadas

    try:
        with xr.open_dataset(ruta_netcdf) as ds:
            # 1. Recorte espacial adaptado a orientación de latitudes de Copernicus.
            # ERA5 entrega latitudes en orden descendente (90→-90), por lo que el
            # slice debe ir del valor mayor al menor: slice(sur_max, norte_min).
            # La lógica de Daniel usa (norte, sur) pero norte < sur en su config
            # Urumea ([43.10, -2.05, 43.35, -1.75] → norte=43.10, sur=43.35),
            # así que para latitudes descendentes necesitamos slice(sur, norte).
            if ds.latitude.values[0] > ds.latitude.values[-1]:
                ds_recortado = ds.sel(latitude=slice(sur, norte), longitude=slice(oeste, este))
            else:
                ds_recortado = ds.sel(latitude=slice(norte, sur), longitude=slice(oeste, este))

            # 2. Media espacial de la cuenca
            ds_medio = ds_recortado.mean(dim=["latitude", "longitude"])

            # 3. Conversión a DataFrame
            df = ds_medio.to_dataframe().reset_index()

            # 4. Armonización temporal
            col_tiempo = next((c for c in ["time", "valid_time", "timestamp"] if c in df.columns), None)
            if col_tiempo:
                df.rename(columns={col_tiempo: "fecha_hora"}, inplace=True)

            # 5. Solo tiempo y variables analíticas
            columnas_a_conservar = ["fecha_hora"]
            for col in df.columns:
                if col not in ["fecha_hora", "latitude", "longitude", "spatial_ref", "crs"]:
                    columnas_a_conservar.append(col)

            df_limpio = df[columnas_a_conservar].copy()
            df_limpio = df_limpio.sort_values("fecha_hora").reset_index(drop=True)
            return df_limpio

    except Exception as e:
        print(f"❌ Error procesando NetCDF: {e}")
        return None
# =============================================================================


# === COPIA LITERAL copernicus_masivo_lluvia_h.py::configurar_credenciales_cds ===
# Adaptación mínima: Lambda solo tiene /tmp escribible; cdsapi respeta
# la variable de entorno CDSAPI_RC para ubicar el fichero de config.
def configurar_credenciales_cds(api_key: str):
    ruta_rc = "/tmp/.cdsapirc"
    with open(ruta_rc, "w") as f:
        f.write("url: https://cds.climate.copernicus.eu/api\n")
        f.write(f"key: {api_key}")
    os.environ["CDSAPI_RC"] = ruta_rc
# ==============================================================================


def lambda_handler(event, context):
    year = int(event["year"])
    month = int(event["month"])

    # Skip si ya existe en S3
    s3_key = f"bronze/era5/{CUENCA}/{year}/{month:02d}/lluvia_temp.csv"
    try:
        S3.head_object(Bucket=BUCKET, Key=s3_key)
        print(f"   ⏭️  Ya existe s3://{BUCKET}/{s3_key}. Saltando.")
        return {"status": "skipped", "s3_key": s3_key}
    except S3.exceptions.ClientError:
        pass  # No existe → descargamos

    # Credenciales CDS desde SSM
    api_key = SSM.get_parameter(Name=CDS_SSM_PARAM, WithDecryption=True)["Parameter"]["Value"].strip()
    configurar_credenciales_cds(api_key)

    # === LITERAL copernicus_masivo_lluvia_h.py::descargar_mes_lluvia líneas 49-96 ===
    import cdsapi
    from datetime import datetime

    print(f"   📡 ERA5-Land {year}-{month:02d} para cuenca '{CUENCA}'...")

    if os.path.exists(NC_TMP):
        os.remove(NC_TMP)

    # Construcción analítica de días del mes
    dias_del_mes = [f"{i:02d}" for i in range(1, 32)]
    if month in [4, 6, 9, 11]:
        dias_del_mes = dias_del_mes[:-1]
    if month == 2:
        dias_del_mes = dias_del_mes[:-3] if (year % 4 == 0) else dias_del_mes[:-2]

    peticion = {
        "variable": ["total_precipitation", "2m_temperature"],
        "year": str(year),
        "month": f"{month:02d}",
        "day": dias_del_mes,
        "time": [f"{i:02d}:00" for i in range(24)],
        "area": COORDENADAS,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }

    try:
        c = cdsapi.Client()
        c.retrieve("reanalysis-era5-land", peticion, NC_TMP)

        df = procesar_netcdf_a_dataframe(NC_TMP, COORDENADAS)

        if df is None:
            raise RuntimeError("procesar_netcdf_a_dataframe devolvió None")

        # Conservar solo fecha_hora + variables analíticas útiles (quitar number, expver, etc.)
        cols_utiles = ["fecha_hora"] + [c for c in df.columns if c in ("tp", "t2m")]
        df = df[cols_utiles]
        if "tp" in df.columns:
            df = df.dropna(subset=["tp"])

        if os.path.exists(NC_TMP):
            os.remove(NC_TMP)

        # Subida a S3
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        S3.put_object(Bucket=BUCKET, Key=s3_key, Body=csv_bytes, ContentType="text/csv")
        print(f"   ✅ {len(df)} filas subidas a s3://{BUCKET}/{s3_key}")
        return {"status": "ok", "rows": int(len(df)), "s3_key": s3_key}

    except Exception as e:
        if os.path.exists(NC_TMP):
            os.remove(NC_TMP)
        raise RuntimeError(f"Error en {year}-{month:02d}: {e}") from e
    # ==========================================================================
