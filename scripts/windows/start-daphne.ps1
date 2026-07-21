$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectRoot

.\venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8000 moveline.asgi:application
