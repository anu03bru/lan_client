$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$zeroAdVersion = "0.28.0"
# TODO: verify the exact x64 installer URL on releases.wildfiregames.com
$installerUrl = "https://releases.wildfiregames.com/0ad-$zeroAdVersion-win64.exe"
$expectedHash = "9b5e1a16d4e0df9c84e052f56fb75da69518d5634c88d2b38db69baee63c16a1"

$hostPort = 20595
$firewallRuleName = "0 A.D. multiplayer (UDP $hostPort)"

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

    # Port used when hosting a game ("Host Game"). Never fails the install.
    Write-Host "==> Open firewall port (UDP $hostPort)"
    $firewallCommand = "`$ErrorActionPreference = 'Stop'; " +
        "Get-NetFirewallRule -DisplayName '$firewallRuleName' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; " +
        "New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPort -Action Allow -Profile Any | Out-Null"
    try {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin) {
            Invoke-Expression $firewallCommand
        }
        else {
            Write-Host "Windows will ask for admin rights to add the firewall rule."
            $firewallProcess = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru `
                -ArgumentList "-NoProfile", "-Command", $firewallCommand
            if ($firewallProcess.ExitCode -ne 0) {
                throw "Firewall command exited with code $($firewallProcess.ExitCode)"
            }
        }
        Write-Host "OK" -ForegroundColor Green
    }
    catch {
        Write-Host "WARNING: Could not open the firewall port. Hosting a game may not work." -ForegroundColor Yellow
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Run in an admin PowerShell: New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPort -Action Allow" -ForegroundColor Yellow
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