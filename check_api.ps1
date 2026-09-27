$ErrorActionPreference = 'SilentlyContinue'
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:1234/v1/models' -TimeoutSec 5
    Write-Host "Status: $($r.StatusCode)"
    Write-Host "Content: $($r.Content)"
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}
