# Windows portability observations

These records concern the authored Rebase implementation running on Windows. They do not execute or establish equivalence with a proprietary Windows reference, and they do not certify desktop or audio-device behavior.

- [Run 39915872920](run-39915872920/observation.json): the Windows x64 C controls passed in Debug and Release (5,442 cases, 18,380 checks per configuration). All six attempted hardware floating-point mode controls were available. The overall milestone remained unaccepted because other lanes exposed SoXR linking and Swift output/reporting failures. Retained JSON records are the downloaded CI artifacts, with hashes in the observation file.

- [Local shared editing](local-shared-editing-20261023/observation.json): 344 Mac tests, 23 portable tests, and observed Mac editing/transport journeys. Source hashes identify the checked implementation. This does not verify a Windows interface.

New runs receive separate records. A later passing run does not rewrite a failed observation or turn a component check into full application parity. The current feature acceptance plan is the [Windows parity ledger](../../../docs/development/windows-parity.md).
