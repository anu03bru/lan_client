#!/bin/sh
# Installs the AssaultCube client on macOS into /Applications.

ASSAULTCUBE_VERSION="1.3.0.2"
IMAGE_NAME="AssaultCube_v${ASSAULTCUBE_VERSION}_LockdownEdition.dmg"
IMAGE_URL="https://github.com/assaultcube/AC/releases/download/v${ASSAULTCUBE_VERSION}/${IMAGE_NAME}"

APPLICATIONS_DIR="/Applications"
TEMP_DIR=""
MOUNT_DIR=""
APP_NAME=""

RED="$(printf "\033[31m")"
GREEN="$(printf "\033[32m")"
RESET="$(printf "\033[0m")"

cleanup() {
    if [ -n "$MOUNT_DIR" ] && [ -d "$MOUNT_DIR" ]; then
        hdiutil detach "$MOUNT_DIR" -quiet >/dev/null 2>&1
    fi
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

check_macos() {
    if [ "$(uname -s)" != "Darwin" ]; then
        echo "This script is for macOS only."
        return 1
    fi
}

check_tools() {
    for tool_name in curl hdiutil xattr; do
        if ! command -v "$tool_name" >/dev/null 2>&1; then
            echo "Missing tool: $tool_name"
            return 1
        fi
    done
}

create_temp_dir() {
    TEMP_DIR="$(mktemp -d)" &&
        MOUNT_DIR="$TEMP_DIR/mount"
}

download_image() {
    curl -L --fail --progress-bar -o "$TEMP_DIR/$IMAGE_NAME" "$IMAGE_URL"
}

mount_image() {
    mkdir "$MOUNT_DIR" &&
        hdiutil attach "$TEMP_DIR/$IMAGE_NAME" -nobrowse -readonly -quiet -mountpoint "$MOUNT_DIR"
}

find_app() {
    app_path="$(find "$MOUNT_DIR" -maxdepth 2 -name "*.app" -type d | head -n 1)"
    if [ -z "$app_path" ]; then
        echo "No .app found in the image."
        return 1
    fi
    APP_NAME="$(basename "$app_path")"
    echo "Found $APP_NAME"
}

copy_app() {
    if [ -d "$APPLICATIONS_DIR/$APP_NAME" ]; then
        echo "Removing old $APPLICATIONS_DIR/$APP_NAME"
        rm -rf "$APPLICATIONS_DIR/$APP_NAME" || return 1
    fi
    cp -R "$MOUNT_DIR/$APP_NAME" "$APPLICATIONS_DIR/"
}

remove_quarantine() {
    xattr -dr com.apple.quarantine "$APPLICATIONS_DIR/$APP_NAME"
}

run_step "Check operating system" "Use install.ps1 on Windows or the Flatpak on Linux." check_macos
run_step "Check required tools" "These tools ship with macOS. Check your PATH." check_tools
run_step "Create temp folder" "Check permissions on /tmp." create_temp_dir
run_step "Download AssaultCube $ASSAULTCUBE_VERSION" "Check the internet connection and the URL: $IMAGE_URL" download_image
run_step "Mount disk image" "The download may be corrupt. Run the script again." mount_image
run_step "Find app in disk image" "Open $TEMP_DIR/$IMAGE_NAME manually and drag the app to Applications." find_app
run_step "Copy app to $APPLICATIONS_DIR" "Your user may need admin rights. Try: sudo sh $0" copy_app
run_step "Remove quarantine flag" "Right-click the app in Applications and choose Open instead." remove_quarantine

echo "${GREEN}Done! Start AssaultCube from Applications.${RESET}"
echo "${GREEN}Multiplayer: open the console and type /connect <server IP> 28763${RESET}"
echo "${GREEN}If it can't connect: System Settings -> Privacy & Security -> Local Network -> enable AssaultCube.${RESET}"