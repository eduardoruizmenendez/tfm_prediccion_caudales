# =====================================================================
# Lambdas one-shot (se invocan manualmente, no tienen EventBridge)
# =====================================================================

# ---------------------------------------------------------------------
# HIDRO HISTORICO — descarga XML anuales Urumea (Open Data Euskadi)
#
# Adaptación literal de descarga_hidro_h.py::descargar_historico_urumea.
# Sin JWT. Invocar una sola vez:
#   aws lambda invoke --function-name tfm-hidro-historico out.json
# Timeout 900 s (máximo Lambda) porque itera 6+ años de XMLs.
# ---------------------------------------------------------------------
data "archive_file" "hidro_historico" {
  type        = "zip"
  source_dir  = "${local.src_dir}/hidro_historico"
  output_path = "${path.module}/.build/hidro_historico.zip"
}

resource "aws_s3_object" "hidro_historico_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "lambda-code/hidro_historico.zip"
  source = data.archive_file.hidro_historico.output_path
  etag   = data.archive_file.hidro_historico.output_md5
}

resource "aws_lambda_function" "hidro_historico" {
  function_name    = "${local.project}-hidro-historico"
  description      = "One-shot: descarga XMLs anuales Urumea (2020→hoy) de Open Data Euskadi — sin JWT"
  role             = aws_iam_role.lambda_exec.arn
  s3_bucket        = aws_s3_object.hidro_historico_code.bucket
  s3_key           = aws_s3_object.hidro_historico_code.key
  source_code_hash = data.archive_file.hidro_historico.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 900
  memory_size      = 512

  environment {
    variables = {
      BUCKET_NAME      = aws_s3_bucket.data_lake.id
      URUMEA_ESTACION  = "C0F0"
    }
  }
}

# ---------------------------------------------------------------------
# COPERNICUS ERA5-LAND — descarga mensual de precipitación y temperatura
#
# Adaptación literal de copernicus_masivo_lluvia_h.py::descargar_mes_lluvia
# + utils_adquisicion_datos.py::procesar_netcdf_a_dataframe.
#
# Requiere imagen Docker en ECR. Construir y hacer push primero:
#   cd terraform/src/copernicus
#   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
#   REGION=eu-south-2
#   aws ecr get-login-password --region $REGION | \
#     docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
#   docker build -t tfm-caudales-copernicus:latest .
#   docker tag tfm-caudales-copernicus:latest \
#     $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/tfm-caudales-copernicus:latest
#   docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/tfm-caudales-copernicus:latest
#
# Después cargar la CDS key en SSM:
#   aws ssm put-parameter --name /tfm/copernicus/cds-api-key \
#     --value "<tu-key>" --type SecureString --overwrite --region eu-south-2
#
# Invocar todos los meses con: terraform/scripts/invoke_copernicus.sh
# ---------------------------------------------------------------------
data "aws_ecr_image" "copernicus_latest" {
  repository_name = aws_ecr_repository.copernicus.name
  image_tag       = "latest"
  depends_on      = [aws_ecr_repository.copernicus]
}

resource "aws_lambda_function" "copernicus" {
  function_name = "${local.project}-copernicus"
  description   = "One-shot por mes: descarga ERA5-Land de Copernicus y sube a bronze/era5/"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"

  image_uri = "${aws_ecr_repository.copernicus.repository_url}@${data.aws_ecr_image.copernicus_latest.id}"

  timeout     = 900
  memory_size = 1024

  environment {
    variables = {
      BUCKET_NAME       = aws_s3_bucket.data_lake.id
      CUENCA            = "urumea"
      CDS_API_KEY_PARAM = aws_ssm_parameter.cds_api_key.name
    }
  }
}
