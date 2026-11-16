param(
    # Remove the game, its user data and its firewall rule instead of installing it
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$zeroAdVersion = "0.28.0"
# TODO: verify the exact x64 installer URL on releases.wildfiregames.com
$installerUrl = "https://releases.wildfiregames.com/0ad-$zeroAdVersion-win64.exe"
$expectedHash = "9b5e1a16d4e0df9c84e052f56fb75da69518d5634c88d2b38db69baee63c16a1"

# Port used when hosting a game ("Host Game")
$hostPorts = "20595"
$firewallRuleName = "0 A.D. multiplayer (UDP $hostPorts)"

$tempDir = Join-Path $env:TEMP ("0AD-" + [guid]::NewGuid())
$installerPath = Join-Path $tempDir "0ad-installer.exe"

function Invoke-Step {
    param(
        [string]$StepName,
        [string]$ErrorHint,
        [scriptblock]$Action
    )

    Write-Host "==> $StepName"
    try {
        & $Action
        Write-Host "OK" -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR: `"$StepName`" failed." -ForegroundColor Red
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Hint: $ErrorHint" -ForegroundColor Red
        throw
    }
}

$script:uninstallFailed = $false

# Like Invoke-Step, but a failure only warns and the uninstall continues.
function Invoke-RemoveStep {
    param(
        [string]$StepName,
        [string]$ErrorHint,
        [scriptblock]$Action
    )

    Write-Host "==> $StepName"
    try {
        & $Action
        Write-Host "OK" -ForegroundColor Green
    }
    catch {
        Write-Host "WARNING: `"$StepName`" failed." -ForegroundColor Yellow
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Hint: $ErrorHint" -ForegroundColor Yellow
        $script:uninstallFailed = $true
    }
}

# Deletes files and folders. Missing ones are skipped.
function Remove-PathIfExists {
    param([string[]]$Path)

    foreach ($itemPath in $Path) {
        if (Test-Path -LiteralPath $itemPath) {
            Remove-Item -LiteralPath $itemPath -Recurse -Force
            Write-Host "Deleted $itemPath"
        }
        else {
            Write-Host "Not found, nothing to do: $itemPath"
        }
    }
}

function Complete-Uninstall {
    if ($script:uninstallFailed) {
        Write-Host "Uninstall finished with warnings. Check the lines above." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Uninstall done." -ForegroundColor Green
    exit 0
}

# Runs a PowerShell command with admin rights. Shows a UAC prompt if this script isn't running as admin.
function Invoke-Elevated {
    param([string]$Command)

    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Invoke-Expression $Command
        return
    }
    # Encoded, so quotes in the command survive the hand-over to the new process
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("`$ErrorActionPreference = 'Stop'; $Command"))
    $elevatedProcess = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru `
        -ArgumentList "-NoProfile", "-EncodedCommand", $encodedCommand
    if ($elevatedProcess.ExitCode -ne 0) {
        throw "Admin command exited with code $($elevatedProcess.ExitCode)"
    }
}

# Runs the silent uninstaller of a program listed in "Apps & features".
function Uninstall-NsisApp {
    param([string]$DisplayNamePattern)

    $uninstallKeys = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $installedApps = @(Get-ItemProperty -Path $uninstallKeys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like $DisplayNamePattern -and $_.UninstallString })
    if ($installedApps.Count -eq 0) {
        Write-Host "Not installed, nothing to do"
        return
    }

    foreach ($installedApp in $installedApps) {
        if ($installedApp.UninstallString -match '^"([^"]+)"') {
            $uninstallerPath = $Matches[1]
        }
        else {
            $uninstallerPath = $installedApp.UninstallString
        }
        if (-not ($uninstallerPath -like "*.exe") -or -not (Test-Path -LiteralPath $uninstallerPath)) {
            throw "Unexpected uninstaller for $($installedApp.DisplayName): $($installedApp.UninstallString)"
        }

        Write-Host "Uninstalling $($installedApp.DisplayName)"
        Invoke-Elevated "Start-Process -FilePath '$uninstallerPath' -ArgumentList '/S' -Wait"

        # The NSIS uninstaller copies itself to a temp folder and returns at once,
        # so wait until its entry is gone from "Apps & features"
        $waitedSeconds = 0
        while ((Test-Path -LiteralPath $installedApp.PSPath) -and $waitedSeconds -lt 300) {
            Start-Sleep -Seconds 2
            $waitedSeconds += 2
        }
        if (Test-Path -LiteralPath $installedApp.PSPath) {
            throw "$($installedApp.DisplayName) is still installed after 5 minutes."
        }
    }
}

function Add-FirewallRule {
    Invoke-Elevated ("Get-NetFirewallRule -DisplayName '$firewallRuleName' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; " +
        "New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPorts -Action Allow -Profile Any | Out-Null")
}

function Remove-FirewallRule {
    if (-not (Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue)) {
        Write-Host "No firewall rule, nothing to do"
        return
    }
    Invoke-Elevated "Remove-NetFirewallRule -DisplayName '$firewallRuleName'"
}

if ($Uninstall) {
    Invoke-RemoveStep "Uninstall 0 A.D." "Uninstall it via Settings -> Apps -> Installed apps." {
        Uninstall-NsisApp -DisplayNamePattern "0 A.D.*"
    }
    Invoke-RemoveStep "Remove firewall rule" "Run in an admin PowerShell: Remove-NetFirewallRule -DisplayName '$firewallRuleName'" {
        Remove-FirewallRule
    }
    Invoke-RemoveStep "Remove user data" "Delete the folders manually." {
        Remove-PathIfExists @(
            (Join-Path $env:APPDATA "0ad"),
            (Join-Path $env:LOCALAPPDATA "0ad"),
            (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "My Games\0ad")
        )
    }
    Complete-Uninstall
}

try {
    Invoke-Step "Create temp folder" "Check permissions on $env:TEMP." {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    }

    Invoke-Step "Download 0 A.D. $zeroAdVersion (about 1.5 GB)" "Check the internet connection and the URL: $installerUrl" {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
    }

    Invoke-Step "Verify download" "The file is corrupt or the URL points to a different version. Try again." {
        $actualHash = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()
        if ($actualHash -ne $expectedHash) {
            throw "Checksum mismatch. Expected $expectedHash, got $actualHash"
        }
    }

    Invoke-Step "Install 0 A.D." "The installer failed. Try running it manually: $installerPath" {
        $installProcess = Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait -PassThru
        if ($installProcess.ExitCode -ne 0) {
            throw "Installer exited with code $($installProcess.ExitCode)"
        }
    }

    # Ports used when hosting a game. Never fails the install.
    Write-Host "==> Open firewall ports (UDP $hostPorts)"
    try {
        Add-FirewallRule
        Write-Host "OK" -ForegroundColor Green
    }
    catch {
        Write-Host "WARNING: Could not open the firewall ports. Hosting a game may not work." -ForegroundColor Yellow
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Run in an admin PowerShell: New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPorts -Action Allow" -ForegroundColor Yellow
    }

    Write-Host "Done! Start 0 A.D. from the start menu." -ForegroundColor Green
    Write-Host "Multiplayer: one player uses 'Host Game', the others 'Join Game' with the host's IP." -ForegroundColor Green
}
catch {
    Write-Host "Installation aborted." -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}