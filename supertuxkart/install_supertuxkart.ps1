$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$stkVersion = "1.5"
$installerName = "SuperTuxKart-$stkVersion-installer-x86_64.exe"
$installerUrl = "https://github.com/supertuxkart/stk-code/releases/download/$stkVersion/$installerName"
$expectedHash = "a1260ebb73dd9da13ec3e37f526f29e494b3b66c00c05fd70767b30a4497d95e"

# 2759 = game server, 2757 = LAN server discovery (needed when hosting via "Create server")
$hostPorts = "2757,2759"
$firewallRuleName = "SuperTuxKart multiplayer (UDP $hostPorts)"

$tempDir = Join-Path $env:TEMP ("SuperTuxKart-" + [guid]::NewGuid())
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

try {
    Invoke-Step "Create temp folder" "Check permissions on $env:TEMP." {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    }

    Invoke-Step "Download SuperTuxKart $stkVersion (about 700 MB)" "Check the internet connection and the URL: $installerUrl" {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
    }

    Invoke-Step "Verify download" "The file is corrupt or the URL points to a different version. Try again." {
        $actualHash = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()
        if ($actualHash -ne $expectedHash) {
            throw "Checksum mismatch. Expected $expectedHash, got $actualHash"
        }
    }

    Invoke-Step "Install SuperTuxKart" "The installer failed. Try running it manually: $installerPath" {
        $installProcess = Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait -PassThru
        if ($installProcess.ExitCode -ne 0) {
            throw "Installer exited with code $($installProcess.ExitCode)"
        }
    }

    # Ports used when hosting a game. Never fails the install.
    Write-Host "==> Open firewall ports (UDP $hostPorts)"
    $firewallCommand = "`$ErrorActionPreference = 'Stop'; " +
        "Get-NetFirewallRule -DisplayName '$firewallRuleName' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; " +
        "New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPorts -Action Allow -Profile Any | Out-Null"
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
        Write-Host "WARNING: Could not open the firewall ports. Hosting a game may not work." -ForegroundColor Yellow
        Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Run in an admin PowerShell: New-NetFirewallRule -DisplayName '$firewallRuleName' -Direction Inbound -Protocol UDP -LocalPort $hostPorts -Action Allow" -ForegroundColor Yellow
    }

    Write-Host "Done! Start SuperTuxKart from the start menu." -ForegroundColor Green
    Write-Host "Multiplayer: Online -> Local network. The host uses 'Create server'." -ForegroundColor Green
}
catch {
    Write-Host "Installation aborted." -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
