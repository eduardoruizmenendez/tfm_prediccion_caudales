# Parameter Store — credenciales de las APIs externas
#
# Diseño:
#   - Terraform los crea con valor placeholder "REPLACE_ME".
#   - El operador los sobreescribe luego vía `aws ssm put-parameter --overwrite`.
#   - `lifecycle.ignore_changes = [value]` impide que `terraform apply`
#     pise los valores reales en sucesivos despliegues.
#   - `lifecycle.prevent_destroy = true` impide que `terraform destroy`
#     borre las claves accidentalmente.
#
# Workflow de destroy → re-apply (sin perder las claves):
#
#   ./scripts/destroy.sh   # state rm + terraform destroy
#   ./scripts/apply.sh     # terraform import + terraform apply

resource "aws_ssm_parameter" "aemet_api_key" {
  name        = "/tfm/aemet/api-key"
  description = "API key personal de AEMET OpenData (cabecera api_key en query string)"
  type        = "SecureString"
  value       = "REPLACE_ME"

  lifecycle {
    ignore_changes  = [value]
    prevent_destroy = true
  }
}

resource "aws_ssm_parameter" "euskalmet_private_key" {
  name        = "/tfm/euskalmet/private-key"
  description = "Clave privada RS256 PEM para firmar el JWT de acceso a Open Data Euskadi (Euskalmet)"
  type        = "SecureString"
  value       = "REPLACE_ME"

  lifecycle {
    ignore_changes  = [value]
    prevent_destroy = true
  }
}

resource "aws_ssm_parameter" "euskalmet_email" {
  name        = "/tfm/euskalmet/email"
  description = "Email registrado en Open Data Euskadi (subject del JWT)"
  type        = "String"
  value       = "REPLACE_ME"

  lifecycle {
    ignore_changes  = [value]
    prevent_destroy = true
  }
}
