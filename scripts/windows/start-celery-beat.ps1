$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectRoot

.\venv\Scripts\celery.exe -A moveline beat -l info
