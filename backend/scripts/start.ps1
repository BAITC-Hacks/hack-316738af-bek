param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $ProjectRoot
$PythonExecutable = Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw 'First run: python -m venv backend\.venv; then install backend/requirements.txt.'
}
$Arguments = @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$Port", '--workers', '1')
if (Test-Path -LiteralPath '.env') { $Arguments += @('--env-file', '.env') }
& $PythonExecutable @Arguments
