#requires -Version 5.1
[CmdletBinding()]
param([string]$TaskName = "Pocket Media Clip Selector", [switch]$ConfigureFirewall)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$windowlessPython = Join-Path $repositoryRoot ".venv\Scripts\pythonw.exe"
$backgroundRunner = Join-Path $PSScriptRoot "run-server-background.pyw"
$firewallRuleName = "Pocket Media Clip Selector (Private LAN)"
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
if ($ConfigureFirewall -and -not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "-ConfigureFirewall needs an elevated PowerShell for the same Windows user. Omit it if the rule is already configured."
}
if (-not (Test-Path -LiteralPath $windowlessPython -PathType Leaf)) { throw "Run scripts\bootstrap-windows.ps1 first." }
Push-Location -LiteralPath $repositoryRoot
try {
    $configuredPort = & $virtualPython -c "from pocket_media_clip_selector.config import load_settings; from pocket_media_clip_selector.library import Library; s=load_settings(); Library(s.working_dir); print(s.port)"
    if ($LASTEXITCODE -ne 0) { throw "Correct .env and the library directory before installing startup." }
} finally { Pop-Location }
$configuredPort = [int](($configuredPort | Select-Object -Last 1).Trim())
if ($ConfigureFirewall) {
    Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $firewallRuleName -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort $configuredPort -Profile Private -RemoteAddress LocalSubnet | Out-Null
}
$action = New-ScheduledTaskAction -Execute $windowlessPython -Argument ('-B "{0}"' -f $backgroundRunner) -WorkingDirectory $repositoryRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity.Name
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$existingTask = Get-ScheduledTask -TaskName $TaskName -TaskPath "\" -ErrorAction SilentlyContinue
if ($null -ne $existingTask) {
    Stop-ScheduledTask -TaskName $TaskName -TaskPath "\"
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $existingTask = Get-ScheduledTask -TaskName $TaskName -TaskPath "\"
        if ($existingTask.State -notin @("Running", "Queued")) { break }
        if ((Get-Date) -ge $deadline) { throw "Timed out stopping '$TaskName'. No replacement server was started." }
        Start-Sleep -Milliseconds 250
    } while ($true)
}
Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -Action $action -Trigger $trigger -Principal $taskPrincipal `
    -Settings $settings -Description "Serves the local media bookmark app at this user's logon." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName -TaskPath "\"
Write-Host "Installed and started '$TaskName' as $($currentIdentity.Name), at user logon." -ForegroundColor Green
Write-Host "Logs: $repositoryRoot\logs. Phone URL: http://<PC IPv4 address from ipconfig>:$configuredPort"
if (-not $ConfigureFirewall) { Write-Host "Firewall was left as configured. To add Private/LocalSubnet rules, run this script elevated with -ConfigureFirewall." }
