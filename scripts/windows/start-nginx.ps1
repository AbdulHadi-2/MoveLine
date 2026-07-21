param(
    [string]$NginxExe = "C:\nginx\nginx.exe"
)

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$nginxPrefix = Join-Path $projectRoot "deploy\nginx"
$configName = "moveline.windows.conf"
$logsPath = Join-Path $nginxPrefix "logs"
$tempPaths = @(
    (Join-Path $nginxPrefix "temp"),
    (Join-Path $nginxPrefix "temp\client_body_temp"),
    (Join-Path $nginxPrefix "temp\proxy_temp"),
    (Join-Path $nginxPrefix "temp\fastcgi_temp"),
    (Join-Path $nginxPrefix "temp\uwsgi_temp"),
    (Join-Path $nginxPrefix "temp\scgi_temp")
)

if (-not (Test-Path $NginxExe)) {
    Write-Error "Nginx executable not found at $NginxExe. Pass -NginxExe with the correct path."
    exit 1
}

if (-not (Test-Path $logsPath)) {
    New-Item -ItemType Directory -Path $logsPath | Out-Null
}

foreach ($tempPath in $tempPaths) {
    if (-not (Test-Path $tempPath)) {
        New-Item -ItemType Directory -Path $tempPath | Out-Null
    }
}

& $NginxExe -p "$nginxPrefix\" -c $configName
