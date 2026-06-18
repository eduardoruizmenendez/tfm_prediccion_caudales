output "data_lake_bucket" {
  description = "Nombre del bucket S3 del Data Lake"
  value       = aws_s3_bucket.data_lake.id
}

output "ecr_predict_url" {
  description = "URL del repositorio ECR donde se sube la imagen de la Lambda de inferencia (cuando se active lambda_predict.tf)"
  value       = aws_ecr_repository.predict.repository_url
}

output "lambdas" {
  description = "Mapa de funciones Lambda creadas (sin predict, que se activa en una segunda fase)"
  value = {
    openmeteo    = aws_lambda_function.openmeteo.function_name
    aemet_actual = aws_lambda_function.aemet_actual.function_name
    hidro_actual = aws_lambda_function.hidro_actual.function_name
    dataset      = aws_lambda_function.dataset.function_name
  }
}

output "ssm_parameters" {
  description = "Paths SSM donde rellenar las credenciales reales (terraform apply los crea con valor placeholder)"
  value = {
    aemet_api_key      = aws_ssm_parameter.aemet_api_key.name
    euskalmet_priv_key = aws_ssm_parameter.euskalmet_private_key.name
    euskalmet_email    = aws_ssm_parameter.euskalmet_email.name
  }
}
