$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # makes Invoke-WebRequest much faster
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$odamexVersion = "12.3.0"
$freedoomVersion = "0.13.0"
$installDir = Join-Path $env:LOCALAPPDATA "OdamexLAN"
$tempDir = Join-Path $env:TEMP ("OdamexLAN-" + [guid]::NewGuid())

$odamexUrl = "https://github.com/odamex/odamex/releases/download/$odamexVersion/odamex-win64-$odamexVersion.zip"
$freedmUrl = "https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedm-$freedoomVersion.zip"
$freedoomUrl = "https://github.com/freedoom/freedoom/releases/download/v$freedoomVersion/freedoom-$freedoomVersion.zip"

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

function Expand-Wads {
    param([string]$ZipPath)

    $extractDir = Join-Path $tempDir ([IO.Path]::GetFileNameWithoutExtension($ZipPath))
    Expand-Archive -Path $ZipPath -DestinationPath $extractDir -Force
    $wadFiles = Get-ChildItem -Path $extractDir -Filter "*.wad" -Recurse
    if ($wadFiles.Count -eq 0) {
        throw "No .wad file found in $ZipPath"
    }
    foreach ($wadFile in $wadFiles) {
        Copy-Item -Path $wadFile.FullName -Destination $installDir -Force
    }
}

try {
    Invoke-Step "Create temp folder" "Check permissions on $env:TEMP." {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    }

    # Odamex
    Invoke-Step "Download Odamex $odamexVersion" "Check the internet connection and the URL: $odamexUrl" {
        Invoke-WebRequest -Uri $odamexUrl -OutFile (Join-Path $tempDir "odamex.zip")
    }

    Invoke-Step "Extract Odamex" "The ZIP may be corrupt. Delete $installDir and try again." {
        Expand-Archive -Path (Join-Path $tempDir "odamex.zip") -DestinationPath $installDir -Force
    }

    # Freedoom
    Invoke-Step "Download FreeDM" "Check the internet connection and the URL: $freedmUrl" {
        Invoke-WebRequest -Uri $freedmUrl -OutFile (Join-Path $tempDir "freedm.zip")
    }

    Invoke-Step "Download Freedoom" "Check the internet connection and the URL: $freedoomUrl" {
        Invoke-WebRequest -Uri $freedoomUrl -OutFile (Join-Path $tempDir "freedoom.zip")
    }

    Invoke-Step "Extract FreeDM" "The ZIP may be corrupt or contain no .wad file." {
        Expand-Wads -ZipPath (Join-Path $tempDir "freedm.zip")
    }

    Invoke-Step "Extract Freedoom" "The ZIP may be corrupt or contain no .wad file." {
        Expand-Wads -ZipPath (Join-Path $tempDir "freedoom.zip")
    }

    Invoke-Step "Verify files" "Files are missing in $installDir." {
        $missingFiles = @("odalaunch.exe", "odamex.exe", "freedm.wad", "freedoom2.wad") |
            Where-Object { -not (Test-Path (Join-Path $installDir $_)) }
        if ($missingFiles) {
            throw "Missing: $($missingFiles -join ", ")"
        }
    }

    # Shortcuts
    Invoke-Step "Create desktop shortcuts" "Could not create the shortcuts. Start the programs manually from $installDir." {
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $shell = New-Object -ComObject WScript.Shell

        $multiplayerShortcut = $shell.CreateShortcut((Join-Path $desktopPath "Odamex LAN.lnk"))
        $multiplayerShortcut.TargetPath = Join-Path $installDir "odalaunch.exe"
        $multiplayerShortcut.WorkingDirectory = $installDir
        $multiplayerShortcut.Save()

        $singleplayerShortcut = $shell.CreateShortcut((Join-Path $desktopPath "Odamex Singleplayer.lnk"))
        $singleplayerShortcut.TargetPath = Join-Path $installDir "odamex.exe"
        $singleplayerShortcut.WorkingDirectory = $installDir
        $singleplayerShortcut.Save()
    }

    Write-Host "Done! Start Odamex with the 'Odamex LAN' shortcut on your desktop." -ForegroundColor Green
}
catch {
    Write-Host "Installation aborted." -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}