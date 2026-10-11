#requires -Version 5.1
[CmdletBinding()]
param([switch]$Reload)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $virtualPython -PathType Leaf)) { throw "Run scripts\bootstrap-windows.ps1 first." }
Push-Location -LiteralPath $repositoryRoot
try {
    $arguments = @("-u", "-m", "pocket_clip_selector")
    if ($Reload) { $arguments += "--reload" }
    # PowerShell 5.1 may classify Python's ordinary stderr logs as ErrorRecords.
    $ErrorActionPreference = "Continue"
    & $virtualPython @arguments
    $serverExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $serverExitCode
