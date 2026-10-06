# Run from an extracted repository with Windows PowerShell 5.1 or later.
# Installs only user-local tools; leaves system Python and PATH unchanged.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$uvVersion = '0.12.19'

# SHA-256 values verified against Microsoft's official winget-pkgs manifests:
# manifests/a/astral-sh/uv/0.12.19/astral-sh.uv.installer.yaml
$releases = @{
    AMD64 = @{
        Archive = 'uv-x86_64-pc-windows-msvc.zip'
        Sha256 = '6DBB02D79E419522F1C500F0ADB1CDDCFF0CDA7D59B0D66EA7F5E3B4A1B2F5F0'
    }
    ARM64 = @{
        Archive = 'uv-aarch64-pc-windows-msvc.zip'
        Sha256 = '115B54CB823BC48260670F5782001ADD6067AC8D98D18C8263A833704E287DE9'
    }
    x86 = @{
        Archive = 'uv-i686-pc-windows-msvc.zip'
        Sha256 = 'E1C2D19D1173A0E9F81BA3F95881AD741808133E372610889FF6870629218C7F'
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This script is for Windows. On Linux/macOS use uv sync and uv run pytest.'
    }
    if (-not (Test-Path (Join-Path $projectDirectory 'uv.lock'))) {
        throw 'Extract the entire project ZIP before running run-tests.cmd.'
    }

    # Enable modern TLS in Windows PowerShell without bypassing certificate checks.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $toolDirectory = Join-Path $env:LOCALAPPDATA "RestApiTestkit\tools\uv-$uvVersion"
    $uvExecutable = Join-Path $toolDirectory 'uv.exe'

    if (-not (Test-Path $uvExecutable)) {
        $architecture = $env:PROCESSOR_ARCHITECTURE
        if ($env:PROCESSOR_ARCHITEW6432) {
            $architecture = $env:PROCESSOR_ARCHITEW6432
        }
        if (-not $releases.ContainsKey($architecture)) {
            throw "Unsupported Windows architecture: $architecture"
        }
        $release = $releases[$architecture]
        $tempDirectory = Join-Path ([IO.Path]::GetTempPath()) ("restkit-" + [guid]::NewGuid())
        New-Item -ItemType Directory -Path $tempDirectory | Out-Null
        try {
            $archivePath = Join-Path $tempDirectory 'uv.zip'
            $downloadUrl = "https://github.com/astral-sh/uv/releases/download/$uvVersion/$($release.Archive)"
            Write-Host "Downloading uv $uvVersion from the official GitHub release..."
            Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $archivePath
            $actualHash = (Get-FileHash -Algorithm SHA256 -Path $archivePath).Hash
            if ($actualHash -ne $release.Sha256) {
                throw 'uv archive checksum mismatch. Installation stopped.'
            }
            $extractDirectory = Join-Path $tempDirectory 'extracted'
            Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDirectory
            if (-not (Test-Path (Join-Path $extractDirectory 'uv.exe'))) {
                throw 'The verified uv archive does not contain uv.exe.'
            }
            New-Item -ItemType Directory -Path $toolDirectory -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $extractDirectory 'uv.exe') -Destination $uvExecutable
        }
        finally {
            Remove-Item -LiteralPath $tempDirectory -Recurse -Force
        }
    }

    Push-Location $projectDirectory
    try {
        Write-Host 'Preparing Python and test dependencies in the project .venv...'
        & $uvExecutable sync --frozen --no-default-groups --group test
        if ($LASTEXITCODE -ne 0) {
            throw "Dependency installation failed (exit code $LASTEXITCODE)."
        }
        Write-Host 'Running REST API tests against the isolated local demo service...'
        & $uvExecutable run --frozen --no-default-groups --group test pytest `
            --alluredir=reports/allure-results --clean-alluredir --junitxml=reports/junit.xml
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed (exit code $LASTEXITCODE). See reports\junit.xml."
        }
        Write-Host "Done. Test results: $projectDirectory\reports"
        Write-Host 'Double-click run-tests.cmd again to rerun the tests.'
    }
    finally {
        Pop-Location
    }
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
