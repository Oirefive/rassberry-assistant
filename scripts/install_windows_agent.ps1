$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot "config\\windows_agent.json"
$startScript = Join-Path $PSScriptRoot "start_windows_agent.ps1"
$tunnelScript = Join-Path $PSScriptRoot "start_windows_tunnel.ps1"
$taskName = "RassberryWindowsAgent"
$tunnelTaskName = "RassberryWindowsTunnel"

if (-not (Test-Path $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json
$port = [int]$config.port

try {
  if (-not (Get-NetFirewallRule -DisplayName $taskName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $taskName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Any | Out-Null
  }
} catch {
  Write-Warning "Не удалось добавить firewall rule автоматически. Возможно, нужны права администратора."
}

$taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`""
schtasks /Create /F /SC ONLOGON /TN $taskName /TR $taskCommand | Out-Null

Start-Process powershell.exe -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-WindowStyle", "Hidden",
  "-File", $startScript
) -WindowStyle Hidden

if (Test-Path (Join-Path $HOME ".ssh\\rassberry_windows_bridge")) {
  $tunnelCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tunnelScript`""
  schtasks /Create /F /SC ONLOGON /TN $tunnelTaskName /TR $tunnelCommand | Out-Null
  Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", $tunnelScript
  ) -WindowStyle Hidden
}

Write-Host "Windows agent installed and started on port $port."
