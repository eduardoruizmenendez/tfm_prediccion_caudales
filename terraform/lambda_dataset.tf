# Lambda de feature engineering (silver/gold)
# Zip subido vía S3 porque incluye pandas + numpy + pyarrow (~80 MB).

data "archive_file" "dataset" {
  type        = "zip"
  source_dir  = "${local.src_dir}/dataset"
  output_path = "${path.module}/.build/dataset.zip"
}

resource "aws_s3_object" "dataset_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "lambda-code/dataset.zip"
  source = data.archive_file.dataset.output_path
  etag   = data.archive_file.dataset.output_md5
}

resource "aws_lambda_function" "dataset" {
  function_name    = "${local.project}-dataset"
  description      = "Generación diaria de la matriz de características desde bronze hacia gold"
  role             = aws_iam_role.lambda_exec.arn
  s3_bucket        = aws_s3_object.dataset_code.bucket
  s3_key           = aws_s3_object.dataset_code.key
  source_code_hash = data.archive_file.dataset.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 1024

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.data_lake.id
      CUENCA      = "urumea"
    }
  }
}
