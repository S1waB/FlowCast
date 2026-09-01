#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================="
echo "   FlowCast - End-to-End Test (Audio Engine)   "
echo "================================================="
echo "This script tests the assembly pipeline with synthesized audio."
echo "It verifies transition capping for short silences and centering for long silences."
echo ""

# Run the python script. Try inside docker first if running, else local python
if docker compose ps | grep -q "api"; then
    echo "🐳 Running inside Docker container 'api'..."
    docker compose exec api python /app/scripts/e2e_test.py
else
    echo "🖥️ Running locally (requires ffmpeg and pydub)..."
    python "$SCRIPT_DIR/e2e_test.py"
fi

echo ""
echo "Done! The output file is located at:"
echo "  backend/output/e2e_test_result.mp3"
echo "Please play it to manually verify the audio levels and transitions."
