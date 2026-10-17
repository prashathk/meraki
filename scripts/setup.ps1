$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked { param([string]$Exe,[string[]]$Arguments) & $Exe @Arguments; if ($LASTEXITCODE -ne 0) { throw "$Exe failed ($LASTEXITCODE)" } }
Invoke-Checked -Exe python -Arguments @('-c','import sys; assert sys.version_info[:2] == (3,13), "Python 3.13 required"')
Invoke-Checked -Exe node -Arguments @('-e','if(Number(process.versions.node.split(".")[0])!==22)process.exit(1)')
if (!(Test-Path '.venv')) { Invoke-Checked -Exe python -Arguments @('-m','venv','.venv') }
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
Invoke-Checked -Exe $python -Arguments @('-m','pip','install','-r','backend/requirements.lock.txt')
New-Item -ItemType Directory -Force data,output | Out-Null
if (!(Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Invoke-Checked -Exe $python -Arguments @('-m','scripts.configure_local')
Push-Location frontend
try { Invoke-Checked -Exe npm.cmd -Arguments @('ci'); Invoke-Checked -Exe npm.cmd -Arguments @('run','build') } finally { Pop-Location }
Write-Output 'Setup complete. See HANDOVER.md for API/worker startup and optional ontology migration. Existing .env was preserved.'
