# Next Steps: ROCm Migration Implementation

## Current Status
Based on the conversation summary, we have completed locally actionable phases 0-5:
- Baseline and freezing of current state
- Environment configuration and diagnostics 
- UI fixes and path corrections
- All 11 tests passing
- Full implementation of locally actionable portions

## Next Phase: Remote ROCm Host Verification and Build

### Prerequisites:
1. Access to the remote ROCm host (u-14073-bcd85560 at radeon-global.anruicloud.com)
2. Proper authentication configured (ANRUI_TOKEN environment variable)
3. The target machine has ROCm tools installed

### Required Actions:

1. **Verify ROCm Host**: Run `scripts/verify_rocm_host.py` on the remote ROCm host
2. **Build HIP-Enabled llama-cpp-python**: Run `scripts/build_llama_cpp_hip.sh` on the remote ROCm host
3. **Validate Build**: Check that HIP symbols are present in the built libraries

### Remote Execution Approach:
Based on the `run_remote_hip_build.py` script, we need to:
- Set environment variables: `ANRUI_BASE` and `ANRUI_TOKEN`  
- Run the remote execution helper to trigger both verification and build

### Implementation Plan:
1. Create documentation for the remote ROCm process
2. Prepare the environment for remote execution
3. Execute the verification phase
4. Execute the build phase

### Key Files:
- `scripts/verify_rocm_host.py` - Verifies ROCm host compatibility
- `scripts/build_llama_cpp_hip.sh` - Builds llama-cpp-python with HIP support
- `scripts/run_remote_hip_build.py` - Helper to drive remote execution

### Environment Variables Needed:
- `ANRUI_BASE` = "https://radeon-global.anruicloud.com/instances/u-14073-bcd85560"  
- `ANRUI_TOKEN` = "amd-oneclick" (or actual token)

### Next Steps:
1. Document current environment setup
2. Configure authentication for remote access
3. Execute verification phase
4. Execute build phase
5. Validate the build results