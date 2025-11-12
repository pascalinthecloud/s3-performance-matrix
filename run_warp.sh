#!/usr/bin/env bash
set -euo pipefail

# === EDIT ME ===
HOST="s3.de.io.cloud.ovh.net:443"   # no scheme; add --tls below
BUCKET="warp-performance-tests"
AK="${AWS_ACCESS_KEY_ID}"
SK="${AWS_SECRET_ACCESS_KEY}"

# Test duration (shorter for more combinations, longer for stability)
DUR="1m"

# Results directory
RESULTS_DIR="results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Ensure bucket exists (uncomment ONE of the following if needed)
# aws --region de s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint=de || true
# mc mb --ignore-existing myovh/"$BUCKET" || true

# Object sizes to test (from small to large)
SIZES=(1KiB 4KiB 16KiB 64KiB 256KiB 1MiB 4MiB 16MiB 64MiB 128MiB)

# Concurrency levels to test (from low to high)
CONCURRENCIES=(1 4 16 64 256 512 1024 2048)

echo "=========================================="
echo "S3 Performance Test Matrix"
echo "=========================================="
echo "Object Sizes: ${SIZES[*]}"
echo "Concurrency Levels: ${CONCURRENCIES[*]}"
echo "Duration per test: $DUR"
echo "Results directory: $RESULTS_DIR"
echo "=========================================="
echo ""

TOTAL_TESTS=$((${#SIZES[@]} * ${#CONCURRENCIES[@]}))
CURRENT_TEST=0

for SZ in "${SIZES[@]}"; do
  for CONC in "${CONCURRENCIES[@]}"; do
    CURRENT_TEST=$((CURRENT_TEST + 1))
    OUT="${RESULTS_DIR}/put_${SZ}_c${CONC}.csv.zst"
    
    echo "[$CURRENT_TEST/$TOTAL_TESTS] Testing: Size=$SZ, Concurrency=$CONC"
    
    if warp put \
      --host "$HOST" --tls \
      --access-key "$AK" --secret-key "$SK" \
      --bucket "$BUCKET" \
      --obj.size "$SZ" \
      --concurrent "$CONC" \
      --duration "$DUR" \
      --benchdata "$OUT" 2>&1 | tee "${RESULTS_DIR}/put_${SZ}_c${CONC}.log"; then
      echo "✓ Completed successfully"
    else
      echo "✗ Failed (exit code: $?)"
    fi
    echo ""
  done
done

echo "=========================================="
echo "All tests completed!"
echo "Results saved to: $RESULTS_DIR"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Run: python3 analyze_results.py $RESULTS_DIR"
echo "2. View the generated charts in ${RESULTS_DIR}/charts/"