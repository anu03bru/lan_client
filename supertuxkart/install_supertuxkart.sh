#!/usr/bin/env bash
set -uo pipefail

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install_supertuxkart.sh${colorReset}"
    exit 1
fi

appId="net.supertuxkart.SuperTuxKart"
expectedVersion="1.5"

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

# Usage: openFirewallPorts "Game name" 1234/udp [5678/udp ...]
# Only does something when ufw is installed and active. Never fails the install.
openFirewallPorts() {
    local gameName="$1"
    shift
    local portSpec
    local failed=0

    echo "==> Open firewall ports (ufw): $*"
    if ! checkCommand ufw; then
        echo -e "${colorGreen}OK (ufw not installed, nothing to do)${colorReset}"
        return 0
    fi
    if ! sudo ufw status | grep -q "Status: active"; then
        echo -e "${colorGreen}OK (ufw not active, nothing to do)${colorReset}"
        return 0
    fi
    for portSpec in "$@"; do
        sudo ufw allow "$portSpec" comment "$gameName" || failed=1
    done
    if [[ "$failed" -eq 0 ]]; then
        echo -e "${colorGreen}OK${colorReset}"
    else
        echo -e "${colorYellow}WARNING: Could not open all firewall ports. Hosting a game may not work.${colorReset}"
        echo -e "${colorYellow}Run manually: sudo ufw allow <port> for each of: $*${colorReset}"
    fi
}

runStep "Check flatpak" "Install it with: sudo pacman -S flatpak" checkCommand flatpak

runStep "Add Flathub remote" \
    "Could not add Flathub. Check the internet connection." \
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

runStep "Install SuperTuxKart (about 700 MB download)" \
    "Flatpak installation failed. Try running: flatpak install --user flathub $appId" \
    flatpak install --user -y --reinstall flathub "$appId"

runStep "Verify installation" \
    "SuperTuxKart not found. Check with: flatpak list" \
    flatpak info --user "$appId"

echo "==> Check version"
installedVersion="$(flatpak info --user "$appId" | grep -m1 "Version:" | sed "s/.*Version: *//")"
if [[ "$installedVersion" == "$expectedVersion"* ]]; then
    echo -e "${colorGreen}OK (version $installedVersion)${colorReset}"
else
    echo -e "${colorYellow}WARNING: Installed version is \"$installedVersion\", expected \"$expectedVersion\".${colorReset}"
    echo -e "${colorYellow}Multiplayer only works reliably if all players have the same version. Tell the organizer.${colorReset}"
fi

# 2759 = game server, 2757 = LAN server discovery (needed when hosting via "Create server")
openFirewallPorts "SuperTuxKart" 2759/udp 2757/udp

echo -e "${colorGreen}Done! Start SuperTuxKart from the start menu.${colorReset}"
echo -e "${colorGreen}Multiplayer: Online -> Local network. The host uses \"Create server\".${colorReset}"