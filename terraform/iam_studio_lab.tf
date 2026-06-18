# Usuario IAM read-only para SageMaker Studio Lab
#
# SageMaker Studio Lab es un servicio gratuito EXTERNO a la cuenta AWS
# (corre en una infra paralela de AWS pensada para estudiantes). Para
# que un notebook en Studio Lab pueda leer del Data Lake, necesita
# unas credenciales AWS con permisos sólo de lectura sobre el bucket.
#
# Aquí provisionamos:
#   - Un usuario IAM dedicado, sin acceso a consola.
#   - Una access key cuyo secret se imprime en el output (sensitive).
#   - Una política inline que SOLO permite GetObject y ListBucket sobre
#     el bucket del Data Lake.

resource "aws_iam_user" "studio_lab_reader" {
  name = "${local.project}-studio-lab-reader"
  path = "/"
}

resource "aws_iam_access_key" "studio_lab_reader" {
  user = aws_iam_user.studio_lab_reader.name
}

resource "aws_iam_user_policy" "studio_lab_reader_s3_ro" {
  name = "data-lake-read-only"
  user = aws_iam_user.studio_lab_reader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:ListBucket"
      ]
      Resource = [
        aws_s3_bucket.data_lake.arn,
        "${aws_s3_bucket.data_lake.arn}/*"
      ]
    }]
  })
}

# Outputs sensibles para pegarlos en Studio Lab
output "studio_lab_access_key_id" {
  description = "AWS_ACCESS_KEY_ID para configurar en SageMaker Studio Lab"
  value       = aws_iam_access_key.studio_lab_reader.id
  sensitive   = true
}

output "studio_lab_secret_access_key" {
  description = "AWS_SECRET_ACCESS_KEY para configurar en SageMaker Studio Lab (sensible)"
  value       = aws_iam_access_key.studio_lab_reader.secret
  sensitive   = true
}
