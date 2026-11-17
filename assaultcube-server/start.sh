#!/bin/sh
# Copies our config files into the install and starts the server
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR/ac"

if [ ! -x "$INSTALL_DIR/server.sh" ]; then
  echo "Server not installed. Run ./setup.sh first."
  exit 1
fi

PASSWORD_FILE="$SCRIPT_DIR/config/serverpwd.cfg"
if [ ! -f "$PASSWORD_FILE" ]; then
  echo "No admin password set. Run: cp config/serverpwd.cfg.example config/serverpwd.cfg"
  echo "Then replace changeme in config/serverpwd.cfg with your own password."
  exit 1
fi
if grep -qx "changeme" "$PASSWORD_FILE"; then
  echo "WARNING: The admin password is still 'changeme'. Change it in config/serverpwd.cfg."
fi

# The .example files are templates, not config
for config_file in "$SCRIPT_DIR"/config/*; do
  case "$config_file" in
    *.example) ;;
    *) cp "$config_file" "$INSTALL_DIR/config/" ;;
  esac
done

cd "$INSTALL_DIR"
exec ./server.sh "$@"
