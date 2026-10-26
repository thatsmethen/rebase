# Documents control-log newline correction

Application run [40261966361](https://github.com/thatsmethen/rebase/actions/runs/40261966361) remains failed. All 92 authored documents-gate cases produced their expected outcomes. The log writer hashed its LF string but text-mode output produced CRLF on Windows. The unchanged log has 92 CRLF line endings; an independent in-memory LF-normalization comparison exactly reproduces the receipt digest. The original file and failed observation were preserved.

The writer now writes explicit UTF-8 bytes and hashes the file it saved. The package still requires the exact file digest; no normalization exception was added to acceptance. WPF was never launched in this run and no package was accepted. A new exact-source Windows run is required.

The separate [component run](../run-40261966425/README.md) passed all thirteen jobs, including the new import tests on both hosts and unchanged audio comparisons. That result does not accept the failed application run.
