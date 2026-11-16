#!/usr/bin/env bash
set -uo pipefail

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install_assaultcube.sh${colorReset}"
    exit 1
fi

usage() {
    echo "Usage: $0 [--uninstall]"
    echo "  (no option)   Install AssaultCube"
    echo "  --uninstall   Remove AssaultCube and its user data"
}

mode="install"
case "${1:-}" in
    "") ;;
    --uninstall) mode="uninstall" ;;
    -h | --help) usage; exit 0 ;;
    *) usage; exit 2 ;;
esac

appId="net.cubers.assault.AssaultCube"

runStep() {
    local stepName="$1"
    local errorHint="$2"
    shift 2

    echo "==> $stepName"
    if ! "$@"; then
        echo -e "${colorRed}ERROR: \"$stepName\" failed.${colorReset}"
        echo -e "${colorRed}Hint: $errorHint${colorReset}"
        exit 1
    fi
    echo -e "${colorGreen}OK${colorReset}"
}

checkCommand() {
    command -v "$1" > /dev/null 2>&1
}

uninstallFailed=0

# Like runStep, but a failure only warns and the uninstall continues.
removeStep() {
    local stepName="$1"
    local errorHint="$2"
    shift 2

    echo "==> $stepName"
    if ! "$@"; then
        echo -e "${colorYellow}WARNING: \"$stepName\" failed.${colorReset}"
        echo -e "${colorYellow}Hint: $errorHint${colorReset}"
        uninstallFailed=1
        return 0
    fi
    echo -e "${colorGreen}OK${colorReset}"
}

# Removes the Flatpak app and its user data (~/.var/app/<appId>).
removeFlatpakApp() {
    local removeAppId="$1"

    if ! checkCommand flatpak; then
        echo "flatpak not installed, nothing to do"
        return 0
    fi
    if flatpak info --user "$removeAppId" > /dev/null 2>&1; then
        flatpak uninstall --user -y --delete-data "$removeAppId" || return 1
    else
        echo "$removeAppId not installed"
    fi
    rm -rf "$HOME/.var/app/$removeAppId"
}

uninstallGame() {
    removeStep "Remove AssaultCube and its user data" \
        "Try running: flatpak uninstall --user --delete-data $appId" \
        removeFlatpakApp "$appId"
}

if [[ "$mode" == "uninstall" ]]; then
    uninstallGame
    if [[ "$uninstallFailed" -eq 0 ]]; then
        echo -e "${colorGreen}Uninstall done.${colorReset}"
    else
        echo -e "${colorYellow}Uninstall finished with warnings. Check the lines above.${colorReset}"
    fi
    exit "$uninstallFailed"
fi

runStep "Check flatpak" "Install it with: sudo pacman -S flatpak" checkCommand flatpak

runStep "Add Flathub remote" \
    "Could not add Flathub. Check the internet connection." \
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

runStep "Install AssaultCube" \
    "Flatpak installation failed. Try running: flatpak install --user flathub $appId" \
    flatpak install --user -y --reinstall flathub "$appId"

runStep "Verify installation" \
    "AssaultCube not found. Check with: flatpak list" \
    flatpak info --user "$appId"

echo -e "${colorGreen}Done! Start AssaultCube from the start menu.${colorReset}"
echo -e "${colorGreen}Multiplayer: Multiplayer -> Join a LAN server.${colorReset}"