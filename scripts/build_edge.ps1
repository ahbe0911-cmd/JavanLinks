$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
dotnet publish edge-host/JavanEdge.csproj -c Release -r win-x64 --self-contained true -o assets/edge-host
if ($LASTEXITCODE -ne 0) { throw "WebView2 host build failed" }
$runtime = Get-ChildItem "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application" -Directory -ErrorAction SilentlyContinue
if (-not $runtime) {
    $installer = Join-Path $env:TEMP "Javan-WebView2Setup.exe"
    Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $installer
    $install = Start-Process -FilePath $installer -ArgumentList "/silent /install" -PassThru -Wait
    if ($install.ExitCode -ne 0) { throw "WebView2 runtime installation failed: $($install.ExitCode)" }
}
$folder = Join-Path $env:TEMP ("JavanEdge-CI-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $folder | Out-Null
try {
    $p = Start-Process -FilePath (Resolve-Path "assets/edge-host/JavanEdge.exe").Path -ArgumentList @("--smoke-test", ('"' + $folder + '"')) -PassThru
    $finished = $p.WaitForExit(120000)
    if (-not $finished) { & taskkill /PID $p.Id /T /F }
    $log = Join-Path $folder "edge-smoke.log"
    if (Test-Path $log) { Get-Content $log -Encoding utf8 }
    if (-not $finished -or $p.ExitCode -ne 0) { throw "Native WebView2 smoke test failed." }
    if (-not (Test-Path $log) -or -not (Select-String -Path $log -SimpleMatch "pass: WebView2 HTTP navigation and live tab reuse verified")) { throw "Native WebView2 assertion missing" }
} finally {
    Remove-Item $folder -Recurse -Force -ErrorAction SilentlyContinue
}
