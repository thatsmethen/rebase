# Windows portability observations

These records concern the authored Rebase implementation running on Windows. They do not execute or establish equivalence with a proprietary Windows reference, and they do not certify desktop or audio-device behavior.

- [Run 39915872920](run-39915872920/observation.json): the Windows x64 C controls passed in Debug and Release (5,442 cases, 18,380 checks per configuration). All six attempted hardware floating-point mode controls were available. The overall milestone remained unaccepted because other lanes exposed SoXR linking and Swift output/reporting failures. Retained JSON records are the downloaded CI artifacts, with hashes in the observation file.

- [Local shared editing](local-shared-editing-20261023/observation.json): 344 Mac tests, 23 portable tests, and observed Mac editing/transport journeys. Source hashes identify the checked implementation. This does not verify a Windows interface.

- [Run 39920053417](run-39920053417/observation.json): native Windows DLL compilation, portable lifecycle controls, public SoXR conversion probe, Swift Debug tests, and both example exports passed. Windows Swift Release discovered zero tests, so the overall run remained unaccepted. Both hosted audio probes explicitly reported no endpoint and no playback.

- [Local shared session](local-session-20261023/observation.json): 45 portable tests, 7 focused Mac store tests, and 16 interactive checks with the bundled legacy-format example. These macOS-hosted implementation checks cover exact example PCM, Save As, and reopen; they do not establish Windows runtime behavior.

- [Run 39925217790](run-39925217790/observation.json) and [application run 39925217794](application-run-39925217794/observation.json): Windows compilation exposed a Foundation/WinSDK UUID ambiguity. The host compiled, but its shared helper prevented a package or window acceptance.

- [Run 39926147551](run-39926147551/observation.json): Windows Debug executed 44 tests and both configurations passed the 16 session checks and exact example export. Release still discovered zero tests. [Application run 39926147513](application-run-39926147513/observation.json) reached the staged helper and found a WPF meter binding failure at startup.

- [Run 39927473852](run-39927473852/observation.json) and [application run 39927473868](application-run-39927473868/observation.json): the real WPF window passed 11 example/edit/save/reopen/export checks and its loaded runtime modules resolved within the staged app or Windows. The captured image is a visual-tree render. Release still discovered zero tests with explicit `/OPT:NOREF`, so no ZIP was created. Audio-device playback remained untested.

- [Run 39929537043](run-39929537043/observation.json): all 13 jobs passed. Windows Debug/Release each executed 44 Swift tests; macOS each executed 45. Disabling cross-module optimization for the optimized Windows test build restored discovery. Production-flag helpers passed their interactive checks and the example PCM matched exactly on both operating systems/configurations. Audio-device playback remained untested.

- [Run 39936173815](run-39936173815/observation.json): all 13 jobs passed after shared source-audition and waveform integration. Windows Debug/Release each executed 60 Swift tests with one opt-in fixture-generator skip; portable macOS each executed 61 with the same skip. Nine shared CPR/fixture checks passed in each lane. Each helper passed 29 process checks, including 17,600 independently checked waveform bins; source-event process checks were not enabled in this component run. The ordinary example PCM remained identical across operating systems/configurations.

- [Application run 39936173813](application-run-39936173813/observation.json): the packaged Windows helper passed 47 process checks, including the exact authored source-event output. The opened WPF window passed 21 checks covering source attachment, undo/redo, export and real waveforms, and the host passed 72 portable controls. Native captures exposed a source-selector label defect, which remains a separate visual acceptance failure. This package is retained as a development result, not a published release. No audio endpoint was available.

- [Run 39939758601](run-39939758601/observation.json): all 13 jobs passed. Windows Debug/Release each executed 70 Swift tests; portable macOS each executed 71, with one opt-in generator skip per lane. Every lane passed 52 helper checks, including the authored source journey and musical ruler. Source/ordinary audio, ruler positions and waveform peaks matched across configurations and platforms.

- [Application run 39939758507](application-run-39939758507/observation.json): 52 packaged-helper checks, 91 host controls and 39 actual-window checks passed. Three client-area images record the corrected source labels, editable inspector, musical ruler and fixed track headers. The downloaded ZIP was independently checked against its CI digest, file manifest and committed example, then privacy reviewed. This is the first Windows development preview; physical input, native dialogs and device playback remain unverified.

- [Run 39946279018](run-39946279018/observation.json): all 13 jobs passed for the Channel/compact-controls candidate. Windows Swift executed 70 tests per configuration, Mac portable 71, public Mac 255; explicit skips and zero failures are recorded. All four helpers passed 52 checks with the same locked example/source audio, waveform and ruler results.

- [Application run 39946278931](application-run-39946278931/observation.json): 54 actual-window checks, 91 host controls and 52 helper checks passed. Both fader sizes match measured thumb coordinates at -96, 0 and +24 dB. Native images show the new Channel/Inspector and compact controls, but root review found an unintended gap below the selected Channel nameplate. Its alignment correction receives a new native gate and separate subsequent evidence. This ZIP has not been independently downloaded or published.

- [Application run 39949650116](application-run-39949650116/observation.json) and [component run 39949650135](run-39949650135/observation.json): the corrected Channel alignment passes the new native gate (686 versus 685.5 DIP). All 55 window checks and all 13 component jobs passed. Three fresh images are accepted for this scoped refinement; the independently downloaded ZIP audit is retained.

- [Component run 39951105337](run-39951105337/observation.json) and [application run 39951105287](application-run-39951105287/observation.json): the portable importer executes six authored controls in each Windows configuration and seven in each macOS configuration, without failures. The app retains 55 passing window checks, 91 host controls and 52 helper checks. Raw CPR review/import is not yet exposed through the Windows session/interface.

New runs receive separate records. A later passing run does not rewrite a failed observation or turn a component check into full application parity. The current feature acceptance plan is the [Windows parity ledger](../../../docs/development/windows-parity.md).

The [local portable CPR import controls](cpr-import-local-20261023/observation.json) retain two raw test reports and exact source hashes. Seven authored cases passed in the macOS portable target; the normal macOS core focused run executed 19 cases with seven explicit private-fixture skips and zero failures. This verifies the shared filesystem adaptation locally; it does not yet establish Windows execution or a Windows review/import interface.
