# Kutaar — Pre-Migration Baseline (plan.md Phase 0)
# Captures repo state, dependency versions, and a quick Ollama latency probe.
# Usage: powershell -File scripts\baseline.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== Kutaar Baseline ===" -ForegroundColor Cyan
Write-Host "Date:    $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# 1. Git state
Write-Host "`n--- Git ---" -ForegroundColor Yellow
Write-Host "Branch:  $(git rev-parse --abbrev-ref HEAD)"
Write-Host "Commit:  $(git rev-parse --short HEAD)"
git status --porcelain | ForEach-Object { Write-Host "  $_" }

# 2. Dependency snapshot
Write-Host "`n--- pip freeze -> scripts/baseline_freeze.txt ---" -ForegroundColor Yellow
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m pip freeze | Out-File -Encoding utf8 scripts\baseline_freeze.txt
Write-Host "Saved $((Get-Content scripts\baseline_freeze.txt).Count) pinned packages."

# 3. Ollama health + latency probe
Write-Host "`n--- Ollama probe ---" -ForegroundColor Yellow
$model = $env:KUTAAR_MODEL
if (-not $model) { $model = "gemma2:2b" }
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    Write-Host "Server:  OK ($($tags.models.Count) models installed)"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $body = @{ model = $model; prompt = "Reply with exactly: baseline-ok"; stream = $false;
               options = @{ num_predict = 16; temperature = 0 } } | ConvertTo-Json
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post `
        -Body $body -ContentType "application/json" -TimeoutSec 120
    $sw.Stop()
    $tps = if ($resp.eval_count -and $sw.Elapsed.TotalSeconds -gt 0) {
        [math]::Round($resp.eval_count / $sw.Elapsed.TotalSeconds, 1)
    } else { "n/a" }
    Write-Host "Model:   $model"
    Write-Host "Latency: $([math]::Round($sw.Elapsed.TotalSeconds, 2))s  eval-tok/s: $tps"
    Write-Host "Reply:   $($resp.response.Trim())"
} catch {
    Write-Host "Ollama probe FAILED: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nBaseline complete." -ForegroundColor Cyan
