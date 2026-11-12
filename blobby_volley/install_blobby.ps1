$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$blobbyVersion = "1.1.1"
$zipName = "blobby2-win32-$blobbyVersion.zip"
$blobbyUrl = "https://sourceforge.net/projects/blobby/files/Blobby%20Volley%202%20(Win32)/$blobbyVersion/$zipName/download"
$expectedHash = "157b8d340bf89d1a6583d689dbb716099762211944c3ca7b588947b6cd7187ff"
$exeName = "blobby.exe"   # TODO: verify after the first extract

$installDir = Join-Path $env:LOCALAPPDATA "BlobbyVolley2"
$tempDir = Join-Path $env:TEMP ("BlobbyVolley2-" + [guid]::NewGuid())
$zipPath = Join-Path $tempDir $zipName

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

    Invoke-Step "Download Blobby Volley 2 $blobbyVersion" "Check the internet connection and the URL: $blobbyUrl" {
        Invoke-WebRequest -Uri $blobbyUrl -OutFile $zipPath -UserAgent "Wget"
    }

    Invoke-Step "Verify download" "The file is corrupt or SourceForge returned an HTML page instead of the ZIP. Try again." {
        $actualHash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
        if ($actualHash -ne $expectedHash) {
            throw "Checksum mismatch. Expected $expectedHash, got $actualHash"
        }
    }

    Invoke-Step "Extract Blobby Volley 2" "The ZIP may be corrupt. Delete $installDir and try again." {
        Expand-Archive -Path $zipPath -DestinationPath $installDir -Force
    }

    Invoke-Step "Find game executable" "No $exeName found in $installDir. Check the ZIP contents and update `$exeName." {
        $script:exeFile = Get-ChildItem -Path $installDir -Filter $exeName -Recurse | Select-Object -First 1
        if (-not $script:exeFile) {
            throw "$exeName not found"
        }
    }

    Invoke-Step "Create desktop shortcut" "Could not create the shortcut. Start the game manually from $($script:exeFile.DirectoryName)." {
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path $desktopPath "Blobby Volley 2.lnk"))
        $shortcut.TargetPath = $script:exeFile.FullName
        $shortcut.WorkingDirectory = $script:exeFile.DirectoryName
        $shortcut.Save()
    }

    Write-Host "Done! Start the game with the 'Blobby Volley 2' shortcut on your desktop." -ForegroundColor Green
}
catch {
    Write-Host "Installation aborted." -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}