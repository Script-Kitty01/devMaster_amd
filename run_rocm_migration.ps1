# ROCm Migration Automation Script
# This script helps with the remote ROCm host verification and build process

Write-Host "=== ROCm Migration Automation ===" -ForegroundColor Green
Write-Host ""

Write-Host "Setting up environment variables..." -ForegroundColor Yellow
$env:ANRUI_BASE = "https://radeon-global.anruicloud.com/instances/u-14073-bcd85560"
$env:ANRUI_TOKEN = "amd-oneclick"

Write-Host ""
Write-Host "Available scripts:" -ForegroundColor Cyan
Write-Host "1. verify_rocm_host.py - Verify ROCm host compatibility" 
Write-Host "2. build_llama_cpp_hip.sh - Build llama-cpp-python with HIP support"
Write-Host "3. run_remote_hip_build.py - Drive remote execution"
Write-Host ""

Write-Host "To run the remote ROCm verification and build:" -ForegroundColor Yellow
Write-Host "1. Ensure ANRUI_TOKEN is set with proper access"
Write-Host "2. Run: python scripts/run_remote_hip_build.py"
Write-Host "3. Follow the prompts to execute verification and build on remote host"
Write-Host ""

Write-Host "See next_steps.md for detailed procedure." -ForegroundColor Gray