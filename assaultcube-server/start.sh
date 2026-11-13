#!/bin/sh
# Copies our config files into the install and starts the server
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR/ac"

if [ ! -x "$INSTALL_DIR/server.sh" ]; then
  echo "Server not installed. Run ./setup.sh <url> first."
  exit 1
fi

cp "$SCRIPT_DIR"/config/* "$INSTALL_DIR/config/"

cd "$INSTALL_DIR"
exec ./server.sh "$@"
