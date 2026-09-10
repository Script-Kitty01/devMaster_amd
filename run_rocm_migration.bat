@echo off
REM ROCm Migration Automation Script
REM This script helps with the remote ROCm host verification and build process

echo.
echo === ROCm Migration Automation ===
echo.

echo Setting up environment variables...
set ANRUI_BASE=https://radeon-global.anruicloud.com/instances/u-14073-bcd85560
set ANRUI_TOKEN=amd-oneclick

echo.
echo Available scripts:
echo 1. verify_rocm_host.py - Verify ROCm host compatibility
echo 2. build_llama_cpp_hip.sh - Build llama-cpp-python with HIP support
echo 3. run_remote_hip_build.py - Drive remote execution

echo.
echo To run the remote ROCm verification and build:
echo 1. Ensure ANRUI_TOKEN is set with proper access
echo 2. Run: python scripts/run_remote_hip_build.py
echo 3. Follow the prompts to execute verification and build on remote host

echo.
echo See next_steps.md for detailed procedure.
echo.

pause