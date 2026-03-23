$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot "windows_agent.py"
$configPath = Join-Path $projectRoot "config\\windows_agent.json"

$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) {
  & $pyLauncher.Source -3 $scriptPath --config $configPath
  exit $LASTEXITCODE
}

$python = Get-Command python.exe -ErrorAction Stop
& $python.Source $scriptPath --config $configPath
exit $LASTEXITCODE
