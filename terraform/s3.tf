# Data Lake — bucket único con organización por prefijos
#   bronze/   datos brutos de APIs (JSON, CSV)
#   silver/   datos limpios en Parquet
#   gold/     matrices de características listas para entrenamiento
#   models/   artefactos de modelos entrenados desde SageMaker Studio Lab

resource "aws_s3_bucket" "data_lake" {
  bucket        = local.bucket_name
  force_destroy = false
}

# Bloqueo total de acceso público (S3 ya cifra por defecto con SSE-S3)
resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
