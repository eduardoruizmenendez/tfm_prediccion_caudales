#!/usr/bin/env bash
# Destruye toda la infraestructura PRESERVANDO los parámetros SSM con las
# credenciales. Hace 'terraform state rm' de cada parámetro antes del
# 'terraform destroy', de modo que Terraform deja de tener constancia de
# ellos y por tanto no los borra en AWS.
#
# Tras este script, los parámetros siguen vivos en SSM con sus valores
# reales. Para volver a desplegar la infraestructura completa usar
# ./scripts/apply.sh, que los recupera vía 'terraform import'.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PARAMS=(
    "aws_ssm_parameter.aemet_api_key"
    "aws_ssm_parameter.euskalmet_private_key"
    "aws_ssm_parameter.euskalmet_email"
)

echo "🔒 Desvinculando parámetros SSM del estado Terraform..."
for p in "${PARAMS[@]}"; do
    if terraform state list | grep -qE "^${p}$"; then
        terraform state rm "$p"
    else
        echo "   · $p ya estaba fuera del estado, saltando"
    fi
done

echo ""
echo "🔥 Lanzando terraform destroy..."
terraform destroy -auto-approve

echo ""
echo "✅ Infraestructura destruida. Los parámetros SSM siguen intactos:"
aws ssm describe-parameters \
    --parameter-filters "Key=Name,Option=BeginsWith,Values=/tfm/" \
    --query "Parameters[].Name" --output table
