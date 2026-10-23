# Windows portability observations

These records concern the authored Rebase implementation running on Windows. They do not execute or establish equivalence with a proprietary Windows reference, and they do not certify desktop or audio-device behavior.

- [Run 39915872920](run-39915872920/observation.json): the Windows x64 C controls passed in Debug and Release (5,442 cases, 18,380 checks per configuration). All six attempted hardware floating-point mode controls were available. The overall milestone remained unaccepted because other lanes exposed SoXR linking and Swift output/reporting failures. Retained JSON records are the downloaded CI artifacts, with hashes in the observation file.

- [Local shared editing](local-shared-editing-20261023/observation.json): 344 Mac tests, 23 portable tests, and observed Mac editing/transport journeys. Source hashes identify the checked implementation. This does not verify a Windows interface.

- [Run 39920053417](run-39920053417/observation.json): native Windows DLL compilation, portable lifecycle controls, public SoXR conversion probe, Swift Debug tests, and both example exports passed. Windows Swift Release discovered zero tests, so the overall run remained unaccepted. Both hosted audio probes explicitly reported no endpoint and no playback.

- [Local shared session](local-session-20261023/observation.json): 45 portable tests, 7 focused Mac store tests, and 16 interactive checks with the bundled legacy-format example. These macOS-hosted implementation checks cover exact example PCM, Save As, and reopen; they do not establish Windows runtime behavior.

New runs receive separate records. A later passing run does not rewrite a failed observation or turn a component check into full application parity. The current feature acceptance plan is the [Windows parity ledger](../../../docs/development/windows-parity.md).
