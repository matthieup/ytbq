#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DENO_DIR="$PROJECT_ROOT/.deno"
DENO_BIN="$DENO_DIR/bin/deno"

if [ -f "$DENO_BIN" ]; then
    echo "Deno is already installed at $DENO_BIN"
    exit 0
fi

echo "Installing deno to $DENO_DIR..."
mkdir -p "$DENO_DIR/bin"

curl -fsSL https://deno.land/install.sh | DENO_INSTALL="$DENO_DIR" sh

echo ""
echo "Deno installed at: $DENO_BIN"
