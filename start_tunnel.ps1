$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTools = Join-Path $PSScriptRoot '.demo-run\tools'
$taskNgrok = Join-Path $taskTools 'ngrok.exe'
if (-not (Test-Path -LiteralPath $taskNgrok)) {
    New-Item -ItemType Directory -Path $taskTools -Force | Out-Null
    $taskZip = Join-Path $taskTools 'ngrok.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' -OutFile $taskZip
    Expand-Archive -LiteralPath $taskZip -DestinationPath $taskTools -Force
}
& $taskNgrok http 'http://127.0.0.1:5000' --inspect=false
