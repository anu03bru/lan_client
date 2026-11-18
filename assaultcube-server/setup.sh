#!/bin/sh
# Installs the AssaultCube dedicated server into ./ac (next to this script).

ASSAULTCUBE_VERSION="1.3.0.2"
ARCHIVE_NAME="AssaultCube_v${ASSAULTCUBE_VERSION}_LockdownEdition_RC1.tar.bz2"
ARCHIVE_URL="https://github.com/assaultcube/AC/releases/download/v${ASSAULTCUBE_VERSION}/${ARCHIVE_NAME}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR/ac"
TEMP_DIR=""

RED="$(printf "\033[31m")"
GREEN="$(printf "\033[32m")"
YELLOW="$(printf "\033[33m")"
RESET="$(printf "\033[0m")"

cleanup() {
    if [ -n "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

# Usage: run_step "Step name" "Hint on failure" command [args...]
run_step() {
    step_name="$1"
    error_hint="$2"
    shift 2

    echo "==> $step_name"
    if "$@"; then
        echo "${GREEN}OK${RESET}"
    else
        echo "${RED}ERROR: \"$step_name\" failed.${RESET}"
        echo "${RED}Hint: $error_hint${RESET}"
        echo "${RED}Installation aborted.${RESET}"
        exit 1
    fi
}

check_not_installed() {
    if [ -d "$INSTALL_DIR" ]; then
        echo "$INSTALL_DIR already exists."
        return 1
    fi
}

check_tools() {
    for tool_name in curl tar bzip2; do
        if ! command -v "$tool_name" >/dev/null 2>&1; then
            echo "Missing tool: $tool_name"
            return 1
        fi
    done
}

create_temp_dir() {
    TEMP_DIR="$(mktemp -d)"
}

download_archive() {
    curl -L --fail --progress-bar -o "$TEMP_DIR/$ARCHIVE_NAME" "$ARCHIVE_URL"
}

extract_archive() {
    mkdir "$TEMP_DIR/extracted" &&
        tar -xjf "$TEMP_DIR/$ARCHIVE_NAME" -C "$TEMP_DIR/extracted"
}

move_to_install_dir() {
    server_script="$(find "$TEMP_DIR/extracted" -maxdepth 3 -name "server.sh" | head -n 1)"
    if [ -z "$server_script" ]; then
        echo "server.sh not found in the archive."
        return 1
    fi
    mv "$(dirname "$server_script")" "$INSTALL_DIR"
}

# 28763 = game port (-f in config/servercmdline.txt), 28764 = info port (game port + 1),
# 28762 = LAN discovery port (fixed in the game source)
FIREWALL_PORTS="28763/udp 28764/udp 28762/udp"

# Only does something when ufw is installed and active. Never fails the install.
open_firewall_ports() {
    echo "==> Open firewall ports (ufw): $FIREWALL_PORTS"
    if ! command -v ufw >/dev/null 2>&1; then
        echo "${GREEN}OK (ufw not installed, nothing to do)${RESET}"
        return 0
    fi
    if ! sudo ufw status | grep -q "Status: active"; then
        echo "${GREEN}OK (ufw not active, nothing to do)${RESET}"
        return 0
    fi
    failed=0
    for port_spec in $FIREWALL_PORTS; do
        sudo ufw allow "$port_spec" comment "AssaultCube server" || failed=1
    done
    if [ "$failed" -eq 0 ]; then
        echo "${GREEN}OK${RESET}"
    else
        echo "${YELLOW}WARNING: Could not open all firewall ports. Players may not find or join the server.${RESET}"
        echo "${YELLOW}Run manually: sudo ufw allow <port> for each of: $FIREWALL_PORTS${RESET}"
    fi
}

run_step "Check existing install" "Delete $INSTALL_DIR to reinstall." check_not_installed
run_step "Check required tools" "Install the missing tool with your package manager." check_tools
run_step "Create temp folder" "Check permissions on /tmp." create_temp_dir
run_step "Download AssaultCube $ASSAULTCUBE_VERSION" "Check the internet connection and the URL: $ARCHIVE_URL" download_archive
run_step "Extract archive" "The download may be corrupt. Run the script again." extract_archive
run_step "Move files to $INSTALL_DIR" "Check write permissions on $SCRIPT_DIR." move_to_install_dir

open_firewall_ports

echo "${GREEN}Done! Set the admin password: cp config/serverpwd.cfg.example config/serverpwd.cfg, then edit it.${RESET}"
echo "${GREEN}Edit the other files in config/ if needed and start the server with ./start.sh${RESET}"