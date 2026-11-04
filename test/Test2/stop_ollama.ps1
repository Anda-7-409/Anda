# Manually stop local Ollama (run_drill.py stops it automatically for fault_demo; this is a fallback)
# Usage: powershell -ExecutionPolicy Bypass -File test\Test2\stop_ollama.ps1
Write-Host "Stopping ollama.exe ..."
taskkill /IM ollama.exe /F 2>$null
taskkill /IM "ollama app.exe" /F 2>$null
Start-Sleep -Seconds 2
try {
    $null = Invoke-WebRequest -Uri http://localhost:11434 -TimeoutSec 2 -UseBasicParsing
    Write-Host "WARNING: Ollama still seems to be running" -ForegroundColor Yellow
} catch {
    Write-Host "Ollama stopped (port 11434 closed)" -ForegroundColor Green
}
