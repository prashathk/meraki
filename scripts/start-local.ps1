$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Create .venv and install backend dependencies first; see README.md.' }
$root = (Get-Location).Path
New-Item -ItemType Directory -Force -Path "$root\data" | Out-Null
Start-Process -WindowStyle Hidden -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','backend.meraki.app:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -RedirectStandardOutput "$root\data\api.log" -RedirectStandardError "$root\data\api-error.log"
Start-Process -WindowStyle Hidden -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList @('-m','worker.run') -WorkingDirectory $root -RedirectStandardOutput "$root\data\worker.log" -RedirectStandardError "$root\data\worker-error.log"
Write-Output 'Meraki: http://127.0.0.1:8000/ (run npm run build in frontend first). Check data logs if a port is already in use.'
