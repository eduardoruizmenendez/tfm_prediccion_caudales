# =====================================================================
# Lambdas de ingesta (zip vía S3)
#
# Los zips superan el límite de subida directa a la Lambda API (~70 MB)
# porque incluyen pandas y, en el caso de hidro_actual, cryptography.
# Por eso subimos primero el zip al propio bucket del Data Lake bajo el
# prefijo lambda-code/ y luego referenciamos el objeto desde Lambda.
# =====================================================================

locals {
  src_dir = "${path.module}/src"
}

# ---------------------------------------------------------------------
# OPENMETEO
# ---------------------------------------------------------------------
data "archive_file" "openmeteo" {
  type        = "zip"
  source_dir  = "${local.src_dir}/openmeteo"
  output_path = "${path.module}/.build/openmeteo.zip"
}

resource "aws_s3_object" "openmeteo_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "lambda-code/openmeteo.zip"
  source = data.archive_file.openmeteo.output_path
  etag   = data.archive_file.openmeteo.output_md5
}

resource "aws_lambda_function" "openmeteo" {
  function_name    = "${local.project}-openmeteo"
  description      = "Ingesta horaria de pronóstico Open-Meteo para la cuenca del Urumea"
  role             = aws_iam_role.lambda_exec.arn
  s3_bucket        = aws_s3_object.openmeteo_code.bucket
  s3_key           = aws_s3_object.openmeteo_code.key
  source_code_hash = data.archive_file.openmeteo.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.data_lake.id
      CUENCA      = "urumea"
    }
  }
}

# ---------------------------------------------------------------------
# AEMET ACTUAL
# ---------------------------------------------------------------------
data "archive_file" "aemet_actual" {
  type        = "zip"
  source_dir  = "${local.src_dir}/aemet_actual"
  output_path = "${path.module}/.build/aemet_actual.zip"
}

resource "aws_s3_object" "aemet_actual_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "lambda-code/aemet_actual.zip"
  source = data.archive_file.aemet_actual.output_path
  etag   = data.archive_file.aemet_actual.output_md5
}

resource "aws_lambda_function" "aemet_actual" {
  function_name    = "${local.project}-aemet-actual"
  description      = "Ingesta horaria AEMET (estación 1024E Igueldo, cuenca Urumea — tal cual config_adquisicion_datos)"
  role             = aws_iam_role.lambda_exec.arn
  s3_bucket        = aws_s3_object.aemet_actual_code.bucket
  s3_key           = aws_s3_object.aemet_actual_code.key
  source_code_hash = data.archive_file.aemet_actual.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUCKET_NAME     = aws_s3_bucket.data_lake.id
      CUENCA          = "urumea"
      AEMET_ESTACION  = "1024E" # Igueldo (literal de config_adquisicion_datos.py)
      AEMET_SSM_PARAM = aws_ssm_parameter.aemet_api_key.name
    }
  }
}

# ---------------------------------------------------------------------
# HIDRO ACTUAL (Euskalmet — Urumea, estación C0F0 Ereñozu)
#
# Adaptación literal de hidro_actual.py::descargar_telemetria_rio (rama
# api_tipo == "euskalmet") + generar_jwt_euskalmet de utils_adquisicion_datos.
# Incluye pyjwt + cryptography para firmar el JWT RS256.
# ---------------------------------------------------------------------
data "archive_file" "hidro_actual" {
  type        = "zip"
  source_dir  = "${local.src_dir}/hidro_actual"
  output_path = "${path.module}/.build/hidro_actual.zip"
}

resource "aws_s3_object" "hidro_actual_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "lambda-code/hidro_actual.zip"
  source = data.archive_file.hidro_actual.output_path
  etag   = data.archive_file.hidro_actual.output_md5
}

resource "aws_lambda_function" "hidro_actual" {
  function_name    = "${local.project}-hidro-actual"
  description      = "Ingesta horaria Euskalmet (Ereñozu C0F0, cuenca Urumea — caudal flow_1)"
  role             = aws_iam_role.lambda_exec.arn
  s3_bucket        = aws_s3_object.hidro_actual_code.bucket
  s3_key           = aws_s3_object.hidro_actual_code.key
  source_code_hash = data.archive_file.hidro_actual.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUCKET_NAME             = aws_s3_bucket.data_lake.id
      CUENCA                  = "urumea"
      EUSKALMET_ESTACION      = "C0F0"
      EUSKALMET_SENSOR_ID     = "CAF0"
      EUSKALMET_MEASURE_TYPE  = "measuresForWater"
      EUSKALMET_MEASURE_ID    = "flow_1"
      EUSKALMET_PRIVKEY_PARAM = aws_ssm_parameter.euskalmet_private_key.name
      EUSKALMET_EMAIL_PARAM   = aws_ssm_parameter.euskalmet_email.name
    }
  }
}
