#!/usr/bin/env bash
set -uo pipefail

odamexVersion="12.3.0"
freedoomVersion="0.13.0"
appId="net.odamex.Odamex"
odamexDir="$HOME/OdamexLAN"
wadDir="$odamexDir/wads"
tempDir="$(mktemp -d)"

odamexUrl="https://github.com/odamex/odamex/releases/download/$odamexVersion/odamex-linux-x86_64-$odamexVersion.flatpak"
freedmUrl="https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedm-$freedoomVersion.zip"
freedoomUrl="https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedoom-$freedoomVersion.zip"

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

# Block running as root
if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./install_doom.sh${colorReset}"
    exit 1
fi

usage() {
    echo "Usage: $0 [--uninstall]"
    echo "  (no option)   Install Odamex and the Freedoom files"
    echo "  --uninstall   Remove Odamex, the Freedoom files and the Odamex user data"
}

mode="install"
case "${1:-}" in
    "") ;;
    --uninstall) mode="uninstall" ;;
    -h | --help) usage; exit 0 ;;
    *) usage; exit 2 ;;
esac

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

removeOdamexRemotes() {
    local remoteName

    if ! checkCommand flatpak; then
        echo "flatpak not installed, nothing to do"
        return 0
    fi
    # The .flatpak bundle install may have added its own remote
    for remoteName in $(flatpak remote-list --user --columns=name | grep -i odamex); do
        flatpak remote-delete --user --force "$remoteName" || return 1
    done
}

resetOdamexOverrides() {
    if ! checkCommand flatpak; then
        echo "flatpak not installed, nothing to do"
        return 0
    fi
    flatpak override --user --reset "$appId"
}

uninstallGame() {
    removeStep "Reset Odamex Flatpak permissions" \
        "Try running: flatpak override --user --reset $appId" \
        resetOdamexOverrides
    removeStep "Remove Odamex and its user data" \
        "Try running: flatpak uninstall --user --delete-data $appId" \
        removeFlatpakApp "$appId"
    removeStep "Remove Odamex Flatpak remote" \
        "List remotes with: flatpak remote-list --user, then: flatpak remote-delete --user <name>" \
        removeOdamexRemotes
    removeStep "Remove $odamexDir" \
        "Delete it manually: rm -rf $odamexDir" \
        rm -rf "$odamexDir"
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

if [[ "$mode" == "uninstall" ]]; then
    uninstallGame
    if [[ "$uninstallFailed" -eq 0 ]]; then
        echo -e "${colorGreen}Uninstall done.${colorReset}"
    else
        echo -e "${colorYellow}Uninstall finished with warnings. Check the lines above.${colorReset}"
    fi
    exit "$uninstallFailed"
fi

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
    flatpak override --user --env=DOOMWADDIR="$wadDir" "$appId"

runStep "Verify WAD files" \
    "WAD files are missing in $wadDir. Check the Freedoom ZIP contents." \
    checkWads

# Permissions
runStep "Give Odamex access to WAD folder" \
    "Flatpak override failed. Is Odamex installed? Check with: flatpak list" \
    flatpak override --user --filesystem="$wadDir:ro" "$appId"

echo -e "${colorGreen}Done! Open Odalaunch and set the WAD folder to: $wadDir${colorReset}"
echo -e "${colorGreen}Want to try it alone first? Start \"Odamex\" from the start menu or run: flatpak run net.odamex.Odamex${colorReset}"