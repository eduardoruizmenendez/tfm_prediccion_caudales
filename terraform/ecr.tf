# Repositorios ECR para Lambdas contenedorizadas
# (dependencias que no caben en un zip de 250 MB)

resource "aws_ecr_repository" "predict" {
  name                 = "${local.project}-predict"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # permite `terraform destroy` sin vaciar antes

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Política de ciclo de vida: solo conserva las últimas 3 imágenes
# para no llenar el almacenamiento de ECR (gratis hasta 500 MB en V1)
resource "aws_ecr_lifecycle_policy" "predict" {
  repository = aws_ecr_repository.predict.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar solo las 3 últimas imágenes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------------
# Copernicus (ERA5-Land) — cdsapi + xarray + netcdf4 no caben en zip
# ---------------------------------------------------------------------
resource "aws_ecr_repository" "copernicus" {
  name                 = "${local.project}-copernicus"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "copernicus" {
  repository = aws_ecr_repository.copernicus.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar solo las 3 últimas imágenes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
