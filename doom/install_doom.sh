#!/usr/bin/env bash
set -uo pipefail

odamexVersion="12.3.0"
freedoomVersion="0.13.0"
wadDir="$HOME/OdamexLAN/wads"
tempDir="$(mktemp -d)"

odamexUrl="https://github.com/odamex/odamex/releases/download/$odamexVersion/odamex-linux-x86_64-$odamexVersion.flatpak"
freedmUrl="https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedm-$freedoomVersion.zip"
freedoomUrl="https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedoom-$freedoomVersion.zip"

colorRed="\033[0;31m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

# Block running as root
if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install.sh${colorReset}"
    exit 1
fi

cleanup() {
    rm -rf "$tempDir"
}
trap cleanup EXIT

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

checkWads() {
    local missingWad=0
    for wadName in "freedm.wad" "freedoom2.wad"; do
        if [[ ! -f "$wadDir/$wadName" ]]; then
            echo -e "${colorRed}Missing: $wadDir/$wadName${colorReset}"
            missingWad=1
        fi
    done
    return "$missingWad"
}

# Preflight checks
runStep "Check curl" "Install it with: sudo pacman -S curl" checkCommand curl
runStep "Check flatpak" "Install it with: sudo pacman -S flatpak" checkCommand flatpak
runStep "Check unzip" "Install it with: sudo pacman -S unzip" checkCommand unzip

# Odamex
runStep "Download Odamex $odamexVersion" \
    "Check the internet connection and the URL: $odamexUrl" \
    curl -fL -o "$tempDir/odamex.flatpak" "$odamexUrl"

runStep "Install Odamex" \
    "Flatpak installation failed. Try running: flatpak install --user $tempDir/odamex.flatpak" \
    flatpak install --user -y "$tempDir/odamex.flatpak"

# Freedoom
runStep "Create WAD folder" \
    "Could not create $wadDir. Check permissions." \
    mkdir -p "$wadDir"

runStep "Download FreeDM" \
    "Check the internet connection and the URL: $freedmUrl" \
    curl -fL -o "$tempDir/freedm.zip" "$freedmUrl"

runStep "Download Freedoom" \
    "Check the internet connection and the URL: $freedoomUrl" \
    curl -fL -o "$tempDir/freedoom.zip" "$freedoomUrl"

runStep "Extract FreeDM" \
    "The ZIP may be corrupt or contain no .wad file." \
    unzip -j -o "$tempDir/freedm.zip" "*.wad" -d "$wadDir"

runStep "Extract Freedoom" \
    "The ZIP may be corrupt or contain no .wad file." \
    unzip -j -o "$tempDir/freedoom.zip" "*.wad" -d "$wadDir"

runStep "Set WAD folder for Odamex" \
    "Flatpak override failed. Is Odamex installed? Check with: flatpak list" \
    flatpak override --user --env=DOOMWADDIR="$wadDir" net.odamex.Odamex

runStep "Verify WAD files" \
    "WAD files are missing in $wadDir. Check the Freedoom ZIP contents." \
    checkWads

# Permissions
runStep "Give Odamex access to WAD folder" \
    "Flatpak override failed. Is Odamex installed? Check with: flatpak list" \
    flatpak override --user --filesystem="$wadDir:ro" net.odamex.Odamex

echo -e "${colorGreen}Done! Open Odalaunch and set the WAD folder to: $wadDir${colorReset}"