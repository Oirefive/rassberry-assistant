$ErrorActionPreference = "Stop"

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$identity = Join-Path $HOME ".ssh\\rassberry_windows_bridge"
$hostIp = "192.168.0.121"
$user = "pi"
$remotePort = 8876

& $ssh `
  -i $identity `
  -NT `
  -o StrictHostKeyChecking=accept-new `
  -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  -R "127.0.0.1:${remotePort}:127.0.0.1:8766" `
  "$user@$hostIp"

exit $LASTEXITCODE
