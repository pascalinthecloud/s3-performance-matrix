#!/usr/bin/env bash
set -euo pipefail

echo "Setting up S3 Warp Performance Testing environment..."
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or later."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate and install dependencies
echo "Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
echo "✓ Python packages installed"

# Check for warp
if ! command -v warp &> /dev/null; then
    echo ""
    echo "⚠️  Warp CLI not found in PATH"
    echo ""
    echo "Please install warp:"
    echo "  1. Download from: https://github.com/minio/warp/releases"
    echo "  2. For macOS: brew install minio/stable/warp"
    echo "  3. Or download binary and add to PATH"
else
    echo "✓ Warp CLI found: $(warp --version 2>&1 | head -n1 || echo 'installed')"
fi

# Check for zstd
if ! command -v zstd &> /dev/null; then
    echo ""
    echo "⚠️  zstd not found (needed for decompressing results)"
    echo "Install with: brew install zstd"
else
    echo "✓ zstd found"
fi

# Check for AWS credentials
echo ""
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "⚠️  AWS credentials not set"
    echo ""
    echo "Please set your credentials:"
    echo "  export AWS_ACCESS_KEY_ID='your-access-key'"
    echo "  export AWS_SECRET_ACCESS_KEY='your-secret-key'"
else
    echo "✓ AWS credentials are set"
fi

echo ""
echo "=================================="
echo "Setup complete!"
echo "=================================="
echo ""
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
echo ""
echo "To run tests:"
echo "  ./run_warp.sh"
echo ""
echo "To analyze results:"
echo "  python3 analyze_results.py results_*/"
echo ""
