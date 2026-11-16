#!/usr/bin/env bash
# Removes all LAN party games installed by the install scripts in this repo:
# the games, their user data, Flatpak overrides and firewall rules.
set -uo pipefail

colorRed="\033[0;31m"
colorYellow="\033[0;33m"
colorGreen="\033[0;32m"
colorReset="\033[0m"

if [[ "$EUID" -eq 0 ]]; then
    echo -e "${colorRed}ERROR: Do not run this script with sudo or as root.${colorReset}"
    echo -e "${colorRed}Run it as your normal user: ./uninstall_all.sh${colorReset}"
    exit 1
fi

repoDir="$(cd "$(dirname "$0")" && pwd)"

# Explicit list: the macOS script and the AssaultCube server are not part of this
gameScripts=(
    "doom/install_doom.sh"
    "blobby_volley/install_blobby.sh"
    "0ad/install_0ad.sh"
    "supertuxkart/install_supertuxkart.sh"
    "assaultcube/install_assaultcube.sh"
)
failedScripts=()

for gameScript in "${gameScripts[@]}"; do
    echo
    echo "######## $gameScript --uninstall"
    if ! bash "$repoDir/$gameScript" --uninstall; then
        failedScripts+=("$gameScript")
    fi
done

echo
echo "######## Flatpak cleanup"
echo "==> Remove Flatpak runtimes no app uses anymore"
if ! command -v flatpak > /dev/null 2>&1; then
    echo -e "${colorGreen}OK (flatpak not installed, nothing to do)${colorReset}"
elif flatpak uninstall --user --unused -y; then
    echo -e "${colorGreen}OK${colorReset}"
else
    echo -e "${colorYellow}WARNING: Could not remove unused runtimes. Try: flatpak uninstall --user --unused${colorReset}"
    failedScripts+=("flatpak cleanup")
fi

echo
if [[ "${#failedScripts[@]}" -eq 0 ]]; then
    echo -e "${colorGreen}All games removed.${colorReset}"
    exit 0
fi
echo -e "${colorYellow}Finished with warnings in:${colorReset}"
for failedScript in "${failedScripts[@]}"; do
    echo -e "${colorYellow}  - $failedScript${colorReset}"
done
exit 1
