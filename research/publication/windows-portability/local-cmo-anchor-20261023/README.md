Local empty-anchor optimization control
=======================================

A standalone Swift 6.2.1/macOS experiment compiled a public empty function in one module and a caller in another, both with Release optimization and whole-module optimization. The default build removed the anchor call from optimized SIL. Disabling cross-module optimization for both modules retained `function_ref` and `apply`. Disabling it only for the caller still removed the call.

This demonstrates the proposed mechanism on this local compiler. It does not establish that the Windows Swift 6.4.1 runner had the same failure, that its DLL was omitted, or that Windows test discovery is repaired. Those require the actual PE import/section inventory and discovered test results. Application source was unchanged by this control.

The receipt records flags and normalized artifact hashes. Temporary and toolchain paths were sanitized; retained SIL is not byte-identical to raw compiler output.
