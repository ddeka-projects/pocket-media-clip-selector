#requires -Version 5.1
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $virtualPython -PathType Leaf)) { throw "Run scripts\bootstrap-windows.ps1 first." }
Push-Location -LiteralPath $repositoryRoot
try {
    Write-Host "Starting one server. Use Ctrl+C to stop. Logs: $repositoryRoot\logs\server.log"
    $ErrorActionPreference = "Continue"
    & $virtualPython -u -m pocket_media_clip_selector
    $serverExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $serverExitCode
