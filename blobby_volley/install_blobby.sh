#!/usr/bin/env bash
set -uo pipefail

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install_blobby.sh${colorReset}"
    exit 1
fi

usage() {
    echo "Usage: $0 [--uninstall]"
    echo "  (no option)   Install Blobby Volley 2"
    echo "  --uninstall   Remove Blobby Volley 2, its user data and firewall rules"
}

mode="install"
case "${1:-}" in
    "") ;;
    --uninstall) mode="uninstall" ;;
    -h | --help) usage; exit 0 ;;
    *) usage; exit 2 ;;
esac

appId="de.blobbyvolley.BlobbyVolley2"
firewallComment="Blobby Volley 2"
firewallPorts=(1234/udp)   # default port when hosting a network game

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

# Deletes all ufw rules whose comment contains the given text.
# Only rules added by these scripts carry that comment, so other rules are never touched.
closeFirewallPorts() {
    local ruleComment="$1"
    local ruleNumber
    local deletedRules=0

    if ! checkCommand ufw; then
        echo "ufw not installed, nothing to do"
        return 0
    fi
    if ! sudo ufw status | grep -q "Status: active"; then
        echo "ufw not active, rules can't be listed. Check later with: sudo ufw show added"
        return 0
    fi
    # One rule at a time, because rule numbers shift after each delete
    while [[ "$deletedRules" -lt 50 ]]; do
        ruleNumber="$(sudo ufw status numbered | grep -F -- "# $ruleComment" | head -n 1 \
            | sed -n 's/^\[ *\([0-9][0-9]*\)\].*/\1/p')"
        if [[ -z "$ruleNumber" ]]; then
            break
        fi
        sudo ufw --force delete "$ruleNumber" > /dev/null || return 1
        deletedRules=$((deletedRules + 1))
    done
    echo "Deleted $deletedRules rule(s)"
}

uninstallGame() {
    removeStep "Remove Blobby Volley 2 and its user data" \
        "Try running: flatpak uninstall --user --delete-data $appId" \
        removeFlatpakApp "$appId"
    removeStep "Close firewall ports (ufw)" \
        "List rules with: sudo ufw status numbered, then delete with: sudo ufw delete <number>" \
        closeFirewallPorts "$firewallComment"
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

runStep "Install Blobby Volley 2" \
    "Flatpak installation failed. Try running: flatpak install --user flathub $appId" \
    flatpak install --user -y --reinstall flathub "$appId"

runStep "Verify installation" \
    "Blobby Volley 2 not found. Check with: flatpak list" \
    flatpak info --user "$appId"

openFirewallPorts "$firewallComment" "${firewallPorts[@]}"

echo -e "${colorGreen}Done! Start Blobby Volley 2 from the start menu.${colorReset}"