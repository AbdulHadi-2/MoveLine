param(
    [string]$NginxExe = "C:\nginx\nginx.exe"
)

if (-not (Test-Path $NginxExe)) {
    Write-Error "Nginx executable not found at $NginxExe. Pass -NginxExe with the correct path."
    exit 1
}

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$nginxPrefix = Join-Path $projectRoot "deploy\nginx"

& $NginxExe -p "$nginxPrefix\" -c "moveline.windows.conf" -s reload
