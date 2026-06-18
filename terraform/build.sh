#!/usr/bin/env bash
# Empaqueta las dependencias Python en cada src/<lambda>/ antes de que
# Terraform haga el zip. Solo es necesario para Lambdas zip cuyos
# requirements.txt declaren paquetes ausentes en el AWS Managed Layer.
#
# Uso:
#   ./build.sh                  # construye todas las Lambdas zip
#   ./build.sh hidro_actual     # construye solo una
#
# Se descargan wheels Linux x86_64 (manylinux2014) para que las
# extensiones C compiladas funcionen en el runtime de Lambda, incluso
# si lanzas este script desde macOS o Windows.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"

LAMBDAS=( "openmeteo" "aemet_actual" "hidro_actual" "dataset" )

if [ $# -gt 0 ]; then
    LAMBDAS=( "$@" )
fi

for fn in "${LAMBDAS[@]}"; do
    REQ="$SRC_DIR/$fn/requirements.txt"
    DIR="$SRC_DIR/$fn"

    if [ ! -d "$DIR" ]; then
        echo "⚠️  $DIR no existe, saltando"
        continue
    fi

    # Borra wheels previos para evitar duplicados
    find "$DIR" -mindepth 1 -maxdepth 1 -type d ! -name "__pycache__" -exec rm -rf {} +

    # Salta si requirements está vacío (solo comentarios)
    if ! grep -v '^\s*#' "$REQ" 2>/dev/null | grep -q .; then
        echo "ℹ️  $fn: requirements vacío, solo handler.py"
        continue
    fi

    echo "📦 Instalando deps de $fn en $DIR"
    pip install \
        --target "$DIR" \
        --platform manylinux2014_x86_64 \
        --python-version 3.11 \
        --implementation cp \
        --only-binary=:all: \
        --upgrade \
        -r "$REQ"
done

echo "✅ Build completo. Ya puedes lanzar 'terraform apply'."
