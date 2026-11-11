# Installs everything the 3d-short skill needs on Windows: Blender, ffmpeg, Python, packages, Piper voice.
#   powershell -ExecutionPolicy Bypass -File engine\setup\install.ps1
# Asks once before installing.  Needs winget (included in Windows 10/11).
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

$answer = Read-Host "Install Blender, ffmpeg, Python 3.12 (via winget), Python packages and the Piper voice? [y/N]"
if ($answer -notmatch "^[Yy]") { Write-Host "Cancelled."; exit 1 }

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if (-not (Test-Path "$env:ProgramFiles\Blender Foundation") -and -not (Have "blender")) {
    winget install --id BlenderFoundation.Blender -e --accept-package-agreements --accept-source-agreements
}
if (-not (Have "ffmpeg")) {
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
}
if (-not (Have "python")) {
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    Write-Host "Python was just installed. Close and reopen the terminal, then run this script again."; exit 0
}

if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.\.venv\Scripts\python.exe -m pip install --quiet -r engine\requirements.txt

New-Item -ItemType Directory -Force assets\voices | Out-Null
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium"
foreach ($f in "en_US-libritts_r-medium.onnx", "en_US-libritts_r-medium.onnx.json") {
    if (-not (Test-Path "assets\voices\$f")) {
        Invoke-WebRequest "$base/${f}?download=true" -OutFile "assets\voices\$f"
    }
}

.\.venv\Scripts\python.exe engine\setup\doctor.py
