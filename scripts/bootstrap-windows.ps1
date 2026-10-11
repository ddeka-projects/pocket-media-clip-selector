#requires -Version 5.1
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $FilePath" }
}

if (-not (Test-Path -LiteralPath $virtualPython -PathType Leaf)) {
    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        Invoke-Checked $launcher.Source @("-3", "-m", "venv", (Join-Path $repositoryRoot ".venv"))
    } else {
        $launcher = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($null -eq $launcher) { throw "Install Python 3.10 or newer (python.org), then run this script again." }
        Invoke-Checked $launcher.Source @("-m", "venv", (Join-Path $repositoryRoot ".venv"))
    }
}
Invoke-Checked $virtualPython @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 'Python 3.10 or newer is required.')")
Invoke-Checked $virtualPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $repositoryRoot "requirements.txt"))
$environmentFile = Join-Path $repositoryRoot ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) {
    Copy-Item -LiteralPath (Join-Path $repositoryRoot ".env.example") -Destination $environmentFile
    Write-Host "Created .env. Set WORKING_DIR to your existing media directory before starting." -ForegroundColor Yellow
}
Write-Host "Ready. Configuration: $environmentFile" -ForegroundColor Green
