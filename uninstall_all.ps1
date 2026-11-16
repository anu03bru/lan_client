param(
    # Set when the script restarted itself with admin rights
    [switch]$Elevated
)

# Removes all LAN party games installed by the install scripts in this repo:
# the games, their user data, desktop shortcuts and firewall rules.
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    # One UAC prompt for everything, instead of one per game.
    # Note: if the admin is a different Windows account, its user folders are cleaned instead of yours.
    Write-Host "Restarting with admin rights..."
    try {
        $elevatedProcess = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru `
            -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Elevated"
    }
    catch {
        Write-Host "ERROR: Admin rights are needed to remove the games and firewall rules." -ForegroundColor Red
        exit 1
    }
    exit $elevatedProcess.ExitCode
}

# Explicit list: the AssaultCube server is not part of this
$gameScripts = @(
    "doom\install_doom.ps1",
    "blobby_volley\install_blobby.ps1",
    "0ad\install_0ad.ps1",
    "supertuxkart\install_supertuxkart.ps1",
    "assaultcube\install_assaultcube.ps1"
)
$failedScripts = @()

foreach ($gameScript in $gameScripts) {
    Write-Host ""
    Write-Host "######## $gameScript -Uninstall"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $gameScript) -Uninstall
    if ($LASTEXITCODE -ne 0) {
        $failedScripts += $gameScript
    }
}

Write-Host ""
if ($failedScripts.Count -eq 0) {
    Write-Host "All games removed." -ForegroundColor Green
    $exitCode = 0
}
else {
    Write-Host "Finished with warnings in:" -ForegroundColor Yellow
    foreach ($failedScript in $failedScripts) {
        Write-Host "  - $failedScript" -ForegroundColor Yellow
    }
    $exitCode = 1
}

# The admin window closes when the script ends, so keep it open to read the output
if ($Elevated) {
    Read-Host "Press Enter to close this window" | Out-Null
}
exit $exitCode
