# Start local Ollama in background (run_drill.py restores it automatically; this is a fallback)
# Usage: powershell -ExecutionPolicy Bypass -File test\Test2\start_ollama.ps1
Write-Host "Starting ollama serve (background)..."
Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $null = Invoke-WebRequest -Uri http://localhost:11434 -TimeoutSec 2 -UseBasicParsing
        Write-Host "Ollama is ready (http://localhost:11434)" -ForegroundColor Green
        exit 0
    } catch { }
}
Write-Host "Not ready within 20s. Run 'ollama serve' manually to see the error." -ForegroundColor Yellow
