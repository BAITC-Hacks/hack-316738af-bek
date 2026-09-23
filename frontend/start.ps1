$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# This workstation has a portable Node installation. A normal Node installation
# is preferred on teammates' machines; nothing is installed globally here.
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $portableNode = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '.tools') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'node-*-win-x64' } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $portableNode) { throw 'Install Node.js 22.12 or newer, then run this script again.' }
    $env:Path = $portableNode.FullName + ';' + $env:Path
}
$env:npm_config_cache = Join-Path $PSScriptRoot '.tools/npm-cache'
if (-not (Test-Path -LiteralPath 'node_modules')) {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Host 'Live: http://127.0.0.1:5173'
Write-Host 'Explicit synthetic demo: http://127.0.0.1:5173/?demo=1'
npm.cmd run dev
