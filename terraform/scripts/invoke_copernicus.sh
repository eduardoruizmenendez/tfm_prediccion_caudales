#!/usr/bin/env bash
# Invoca la Lambda copernicus para cada mes 2020-01 → hoy.
# Lanza hasta MAX_CONCURRENT invocaciones en paralelo.
# Los meses ya existentes en S3 los salta la propia Lambda (skip logic).
#
# Uso:
#   ./scripts/invoke_copernicus.sh
#   ./scripts/invoke_copernicus.sh 2023 01   # desde un mes concreto

set -euo pipefail

FUNCTION="tfm-caudales-copernicus"
REGION="eu-south-2"
MAX_CONCURRENT=5   # CDS cola tiene límite; 5 es seguro
OUT_DIR="/tmp/copernicus_invoke"
mkdir -p "$OUT_DIR"

START_YEAR=${1:-2020}
START_MONTH=${2:-1}

NOW_YEAR=$(date +%Y)
NOW_MONTH=$(date +%-m)

echo "🚀 Invocando $FUNCTION para meses $START_YEAR-$(printf '%02d' $START_MONTH) → $NOW_YEAR-$(printf '%02d' $NOW_MONTH)"
echo "   Concurrencia máxima: $MAX_CONCURRENT"

pids=()

invoke_month() {
    local year=$1 month=$2
    local label="${year}-$(printf '%02d' $month)"
    local out="$OUT_DIR/${label}.json"

    echo "   ▶ Lanzando $label"
    aws lambda invoke \
        --function-name "$FUNCTION" \
        --region "$REGION" \
        --cli-read-timeout 960 \
        --payload "{\"year\": $year, \"month\": $month}" \
        "$out" > /dev/null 2>&1

    status=$(python3 -c "import json,sys; d=json.load(open('$out')); print(d.get('status','error'))" 2>/dev/null || echo "error")
    echo "   ✅ $label → $status"
}

year=$START_YEAR
month=$START_MONTH

while true; do
    # Condición de fin
    if [ "$year" -gt "$NOW_YEAR" ]; then break; fi
    if [ "$year" -eq "$NOW_YEAR" ] && [ "$month" -gt "$NOW_MONTH" ]; then break; fi

    # Lanzar en background
    invoke_month "$year" "$month" &
    pids+=($!)

    # Control de concurrencia: esperar cuando llegamos al límite
    if [ "${#pids[@]}" -ge "$MAX_CONCURRENT" ]; then
        wait "${pids[0]}"
        pids=("${pids[@]:1}")
    fi

    # Avanzar mes
    if [ "$month" -eq 12 ]; then
        month=1
        year=$((year + 1))
    else
        month=$((month + 1))
    fi
done

# Esperar al resto
for pid in "${pids[@]}"; do
    wait "$pid"
done

echo ""
echo "🏆 Todos los meses procesados. Resultados en $OUT_DIR/"
echo "   Resumen:"
for f in "$OUT_DIR"/*.json; do
    label=$(basename "$f" .json)
    status=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('status','?'))" 2>/dev/null || echo "error")
    rows=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('rows',''))" 2>/dev/null || echo "")
    echo "   $label → $status $rows"
done
