param(
    # Remove the game, its user data and its firewall rule instead of installing it
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$assaultCubeVersion = "1.3.0.2"
$installerName = "AssaultCube_v$($assaultCubeVersion)_LockdownEdition.exe"
# TODO: verify this URL on the GitHub release page
$installerUrl = "https://github.com/assaultcube/AC/releases/download/v$assaultCubeVersion/$installerName"

$tempDir = Join-Path $env:TEMP ("AssaultCube-" + [guid]::NewGuid())
$installerPath = Join-Path $tempDir $installerName

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

if ($Uninstall) {
    Invoke-RemoveStep "Uninstall AssaultCube" "Uninstall it via Settings -> Apps -> Installed apps." {
        Uninstall-NsisApp -DisplayNamePattern "AssaultCube*"
    }
    Invoke-RemoveStep "Remove user data" "Delete the folders manually." {
        # TODO: verify the user data folder on a Windows test machine
        Remove-PathIfExists @(
            (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "My Games\AssaultCube")
        )
    }
    Complete-Uninstall
}

try {
    Invoke-Step "Create temp folder" "Check permissions on $env:TEMP." {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    }

    Invoke-Step "Download AssaultCube $assaultCubeVersion" "Check the internet connection and the URL: $installerUrl" {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
    }

    Invoke-Step "Install AssaultCube (admin prompt will appear)" "The installer failed or the admin prompt was declined. Try running it manually: $installerPath" {
        $installProcess = Start-Process -FilePath $installerPath -ArgumentList "/S" -Verb RunAs -Wait -PassThru
        if ($installProcess.ExitCode -ne 0) {
            throw "Installer exited with code $($installProcess.ExitCode)"
        }
    }

    Write-Host "Done! Start AssaultCube from the start menu." -ForegroundColor Green
    Write-Host "Multiplayer: Multiplayer -> Join a LAN server." -ForegroundColor Green
}
catch {
    Write-Host "Installation aborted." -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}