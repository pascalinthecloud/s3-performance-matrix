#!/usr/bin/env bash
set -euo pipefail

# Script to verify parsed results against warp analyze output

if [ $# -lt 1 ]; then
    echo "Usage: $0 <results_directory>"
    exit 1
fi

RESULTS_DIR="$1"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "Error: Directory not found: $RESULTS_DIR"
    exit 1
fi

echo "=========================================="
echo "Verifying Results with Warp Analyze"
echo "=========================================="
echo ""

# Create verification output directory
VERIFY_DIR="${RESULTS_DIR}/verification"
mkdir -p "$VERIFY_DIR"

# Find all .csv.zst.json.zst files
shopt -s nullglob
FILES=("${RESULTS_DIR}"/*.csv.zst.json.zst)

if [ ${#FILES[@]} -eq 0 ]; then
    echo "No .csv.zst.json.zst files found in $RESULTS_DIR"
    exit 1
fi

echo "Found ${#FILES[@]} result files to verify"
echo ""

# Process each file
for FILE in "${FILES[@]}"; do
    BASENAME=$(basename "$FILE" .csv.zst.json.zst)
    echo "=========================================="
    echo "File: $BASENAME"
    echo "=========================================="
    
    # Run warp analyze and display output
    warp analyze "$FILE" 2>&1 || echo "✗ Failed to analyze"
    echo ""
done

echo "=========================================="
echo "Verification Complete"
echo "=========================================="
