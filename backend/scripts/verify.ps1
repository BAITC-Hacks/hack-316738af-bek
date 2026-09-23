$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $ProjectRoot
$PythonExecutable = Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'
& $PythonExecutable -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable -m ruff check backend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable -m ruff format --check backend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonExecutable -m pytest backend/tests -q -W error --cov=backend.app --cov-config=backend/pyproject.toml --cov-report=term-missing --cov-report=json:backend/test-results/coverage.json --junitxml=backend/test-results/junit.xml
exit $LASTEXITCODE
