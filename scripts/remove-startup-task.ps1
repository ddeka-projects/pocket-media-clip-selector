#requires -Version 5.1
[CmdletBinding()]
param([string]$TaskName = "Pocket Media Clip Selector", [switch]$RemoveFirewall)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
if ($RemoveFirewall) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "The task is removed. Run elevated with -RemoveFirewall to also remove its firewall rules."
    }
    foreach ($name in @("Pocket Media Clip Selector (Private LAN)")) {
        Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
}
Write-Host "Startup task stopped and removed. Media and saved selections are retained."
