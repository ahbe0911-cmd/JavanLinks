param([string]$Python = "", [switch]$SkipInstall, [switch]$Onedir)
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
& node --test tests/test_accounting_js.cjs
if ($LASTEXITCODE -ne 0) { throw "Accounting JavaScript tests failed" }
$bundleMode = if ($Onedir) { '--onedir' } else { '--onefile' }
$distPath = if ($Onedir) { 'dist-fast' } else { 'dist' }
Run-Python -m PyInstaller --noconfirm --clean $bundleMode --windowed --noupx --name JavanLinks --distpath $distPath --icon assets/javan.ico --version-file scripts/version_info.txt --add-data "assets;assets" main.py
$exe = if ($Onedir) { (Resolve-Path "dist-fast\JavanLinks\JavanLinks.exe").Path } else { (Resolve-Path "dist\JavanLinks.exe").Path }
$smokeLog = Join-Path ([System.IO.Path]::GetTempPath()) ("JavanLinks-startup-" + [guid]::NewGuid().ToString("N") + ".log")
$env:JAVAN_CI_SMOKE_LOG = $smokeLog
try {
    $process = Start-Process -FilePath $exe -ArgumentList "--smoke-test" -PassThru
    $finished = $process.WaitForExit(180000)
    if (-not $finished) {
        & taskkill /PID $process.Id /T /F
    }
    if (Test-Path $smokeLog) { Get-Content -LiteralPath $smokeLog -Encoding utf8 }
    if (-not $finished) { throw "Frozen WebEngine startup test timed out." }
    if ($process.ExitCode -ne 0) { throw "Frozen WebEngine startup test failed: $($process.ExitCode)" }
} finally {
    Remove-Item Env:JAVAN_CI_SMOKE_LOG -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $smokeLog -ErrorAction SilentlyContinue
}
# Verify actual accounting storage survives two independent frozen processes.
$probe = Join-Path ([System.IO.Path]::GetTempPath()) ("JavanLinks-probe-" + [guid]::NewGuid().ToString("N"))
try {
    foreach ($mode in @("seed", "write", "read")) {
        $probeProcess = Start-Process -FilePath $exe -ArgumentList @("--accounting-probe-$mode", ('"' + $probe + '"')) -PassThru
        if (-not $probeProcess.WaitForExit(180000)) {
            & taskkill /PID $probeProcess.Id /T /F
            $probeLog = Join-Path $probe "probe-$mode.log"
            if (Test-Path $probeLog) { Get-Content -LiteralPath $probeLog -Encoding utf8 }
            throw "Accounting persistence probe $mode timed out."
        }
        $probeLog = Join-Path $probe "probe-$mode.log"
        if (Test-Path $probeLog) { Get-Content -LiteralPath $probeLog -Encoding utf8 }
        if ($probeProcess.ExitCode -ne 0) { throw "Accounting persistence probe $mode failed: $($probeProcess.ExitCode)" }
        Write-Host "Accounting probe $mode passed."
    }
} finally {
    if (Test-Path $probe) { Remove-Item -Path $probe -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($Onedir) {
    # Preserve Qt's directory layout; do not send only the nested executable.
    Run-Python -c "import shutil; shutil.make_archive('dist-fast/JavanLinks-Fast-Windows-x64','zip','dist-fast','JavanLinks')"
    $zip = 'dist-fast\JavanLinks-Fast-Windows-x64.zip'
    $hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -Path "$zip.sha256" -Value "$hash  JavanLinks-Fast-Windows-x64.zip" -Encoding ascii
} else {
    $hash = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -Path "dist\JavanLinks.exe.sha256" -Value "$hash  JavanLinks.exe" -Encoding ascii
}
Write-Host "Build and frozen startup test succeeded: $exe"
