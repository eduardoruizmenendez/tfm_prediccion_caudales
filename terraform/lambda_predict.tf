# Lambda de inferencia (contenedor Docker en ECR)
#
# Construcción y push de la imagen NO la gestiona Terraform — se hace
# fuera con un script:
#
#   cd terraform/src/predict
#   docker build -t tfm-caudales-predict:latest .
#   aws ecr get-login-password --region eu-south-2 | \
#       docker login --username AWS --password-stdin <accountId>.dkr.ecr.eu-south-2.amazonaws.com
#   docker tag tfm-caudales-predict:latest <accountId>.dkr.ecr.eu-south-2.amazonaws.com/tfm-caudales-predict:latest
#   docker push <accountId>.dkr.ecr.eu-south-2.amazonaws.com/tfm-caudales-predict:latest
#
# Después: terraform apply
# Terraform detecta el cambio porque image_uri usa el digest, no el tag.

data "aws_ecr_image" "predict_latest" {
  repository_name = aws_ecr_repository.predict.name
  image_tag       = "latest"
  depends_on      = [aws_ecr_repository.predict]
}

resource "aws_lambda_function" "predict" {
  function_name = "${local.project}-predict"
  description   = "Inferencia XGBoost base (V1) sobre los últimos datos del Data Lake"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"

  # Usar el digest (no el tag :latest) hace que Terraform detecte
  # automáticamente cambios cuando se sube una nueva imagen y actualice
  # la Lambda en el siguiente apply.
  image_uri = "${aws_ecr_repository.predict.repository_url}@${data.aws_ecr_image.predict_latest.id}"

  timeout     = 60
  memory_size = 2048

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.data_lake.id
      CUENCA      = "urumea"
    }
  }
}

# NOTA V1: Lambda Function URL no se crea en eu-south-2 por un bug
# conocido en regiones recientes ("Unable to determine service/
# operation name to be authorized"). Para V1 la inferencia se invoca
# directamente con `aws lambda invoke`, lo cual es además más
# profesional que un endpoint HTTPS abierto.
#
# En V2, exponer públicamente vía API Gateway HTTP API (tier gratuito
# 1M req/mes durante 12 meses) o esperar a que AWS habilite Function
# URLs en eu-south-2.
