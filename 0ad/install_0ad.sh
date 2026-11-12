#!/usr/bin/env bash
set -uo pipefail

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install_0ad.sh${colorReset}"
    exit 1
fi

appId="com.play0ad.zeroad"
expectedVersion="0.28.0"

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

runStep "Check flatpak" "Install it with: sudo pacman -S flatpak" checkCommand flatpak

runStep "Add Flathub remote" \
    "Could not add Flathub. Check the internet connection." \
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

runStep "Install 0 A.D. (about 1.7 GB download)" \
    "Flatpak installation failed. Try running: flatpak install --user flathub $appId" \
    flatpak install --user -y --reinstall flathub "$appId"

runStep "Verify installation" \
    "0 A.D. not found. Check with: flatpak list" \
    flatpak info --user "$appId"

echo "==> Check version"
installedVersion="$(flatpak info --user "$appId" | grep -m1 "Version:" | sed "s/.*Version: *//")"
if [[ "$installedVersion" == "$expectedVersion" ]]; then
    echo -e "${colorGreen}OK (version $installedVersion)${colorReset}"
else
    echo -e "${colorYellow}WARNING: Installed version is \"$installedVersion\", expected \"$expectedVersion\".${colorReset}"
    echo -e "${colorYellow}Multiplayer only works if all players have the same version. Tell the organizer.${colorReset}"
fi

echo -e "${colorGreen}Done! Start 0 A.D. from the start menu.${colorReset}"
echo -e "${colorGreen}Multiplayer: one player uses \"Host Game\", the others \"Join Game\" with the host's IP.${colorReset}"