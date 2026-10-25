# Run Beru Hub with LAN Binding and Firewall Guidance

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       BERU HUB - LAN RUNTIME LAUNCHER    " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Discover active IPv4 addresses
$lanIps = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" } |
    Select-Object -ExpandProperty IPAddress

$primaryIp = $lanIps | Select-Object -First 1
if (-not $primaryIp) {
    $primaryIp = "127.0.0.1"
}

Write-Host ""
Write-Host "Active LAN IP Address(es) detected:" -ForegroundColor Green
foreach ($ip in $lanIps) {
    Write-Host "  -> http://$($ip):8000" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Configure your Phone & PC Beru apps with:" -ForegroundColor White
Write-Host "  Hub URL: http://$($primaryIp):8000" -ForegroundColor Cyan -NoNewline
Write-Host " (or your specific Wi-Fi LAN IP above)" -ForegroundColor Gray

Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Windows Firewall Rule (Run once in Admin PowerShell):" -ForegroundColor Magenta
Write-Host '  New-NetFirewallRule -DisplayName "Beru Hub" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private' -ForegroundColor White
Write-Host "To remove rule later after testing:" -ForegroundColor DarkGray
Write-Host '  Remove-NetFirewallRule -DisplayName "Beru Hub"' -ForegroundColor DarkGray
Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Starting Uvicorn Hub on 0.0.0.0:8000..." -ForegroundColor Green

python -m uvicorn hub.main:app --host 0.0.0.0 --port 8000 --reload
