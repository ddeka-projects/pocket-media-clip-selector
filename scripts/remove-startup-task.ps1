#requires -Version 5.1
[CmdletBinding()]
param([string]$TaskName = "Pocket Media Clip Selector", [switch]$RemoveFirewall)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($RemoveFirewall) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "-RemoveFirewall needs an elevated PowerShell for the same Windows user. No changes were made."
    }
}
$task = Get-ScheduledTask -TaskName $TaskName -TaskPath "\" -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName -TaskPath "\"
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath "\" -Confirm:$false
}
if ($RemoveFirewall) {
    foreach ($name in @("Pocket Media Clip Selector (Private LAN)")) {
        Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
}
else {
    Write-Host "Firewall was left as configured. To also remove its rules, run this script elevated with -RemoveFirewall."
}
Write-Host "Startup task stopped and removed. Media and bookmarks are retained."
