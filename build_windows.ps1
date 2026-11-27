param([string]$Python = "", [switch]$SkipInstall)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Run-Python {
    & $script:Python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args (exit $LASTEXITCODE)" }
}
if (-not $Python) {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12 x64 is required to build locally." }
    }
    $Python = (Resolve-Path ".venv\Scripts\python.exe").Path
}
if (-not $SkipInstall) {
    Run-Python -m pip install --upgrade pip
    Run-Python -m pip install -r requirements-build.txt
}
Run-Python -c "import struct; assert struct.calcsize('P') == 8, '64-bit Python required'"
Run-Python scripts/prepare_assets.py
Run-Python -m compileall -q main.py javan tests scripts
Run-Python -m unittest discover -s tests -v
Run-Python -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name JavanLinks --icon assets/javan.ico --version-file scripts/version_info.txt --add-data "assets;assets" main.py
$exe = (Resolve-Path "dist\JavanLinks.exe").Path
$process = Start-Process -FilePath $exe -ArgumentList "--smoke-test" -PassThru
if (-not $process.WaitForExit(180000)) {
    & taskkill /PID $process.Id /T /F
    throw "Frozen WebEngine startup test timed out."
}
if ($process.ExitCode -ne 0) { throw "Frozen WebEngine startup test failed: $($process.ExitCode)" }
$hash = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -Path "dist\JavanLinks.exe.sha256" -Value "$hash  JavanLinks.exe" -Encoding ascii
Write-Host "Build and frozen startup test succeeded: $exe"
