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