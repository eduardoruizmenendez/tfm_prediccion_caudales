#!/usr/bin/env bash
# Despliega toda la infraestructura.
#
# Si los parámetros SSM ya existen en AWS (porque destroy.sh los preservó),
# los recupera vía 'terraform import' antes de hacer 'terraform apply' para
# que Terraform vuelva a gestionarlos sin intentar crearlos (lo cual
# fallaría con "ParameterAlreadyExists").
#
# Si los parámetros aún no existen, los crea con valor placeholder
# "REPLACE_ME" durante el apply. Luego hay que sobreescribirlos manualmente:
#   aws ssm put-parameter --name /tfm/aemet/api-key --value ... --overwrite

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

declare -A PARAMS=(
    [aws_ssm_parameter.aemet_api_key]="/tfm/aemet/api-key"
    [aws_ssm_parameter.euskalmet_private_key]="/tfm/euskalmet/private-key"
    [aws_ssm_parameter.euskalmet_email]="/tfm/euskalmet/email"
)

echo "🔍 Comprobando estado de los parámetros SSM..."

for tf_address in "${!PARAMS[@]}"; do
    ssm_name="${PARAMS[$tf_address]}"

    # Caso 1: ya está en el estado de Terraform → nada que hacer
    if terraform state list 2>/dev/null | grep -qE "^${tf_address}$"; then
        echo "   · $tf_address ya en estado de Terraform, OK"
        continue
    fi

    # Caso 2: existe en AWS pero no en el estado → importar
    if aws ssm get-parameter --name "$ssm_name" --query "Parameter.Name" --output text 2>/dev/null >/dev/null; then
        echo "   · $tf_address existe en AWS, importando..."
        terraform import "$tf_address" "$ssm_name"
        continue
    fi

    # Caso 3: no existe en ningún sitio → lo creará terraform apply abajo
    echo "   · $tf_address aún no existe, lo creará terraform apply"
done

echo ""
echo "🏗️  Lanzando terraform apply..."
terraform apply -auto-approve

echo ""
echo "✅ Infraestructura desplegada."
echo ""
echo "Recuerda sobreescribir los placeholders REPLACE_ME con las claves reales:"
echo "   aws ssm put-parameter --name /tfm/aemet/api-key       --value <jwt>    --type SecureString --overwrite"
echo "   aws ssm put-parameter --name /tfm/euskalmet/private-key --value file://./euskalmet_private.pem --type SecureString --overwrite"
echo "   aws ssm put-parameter --name /tfm/euskalmet/email     --value <email> --type String       --overwrite"
