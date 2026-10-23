# Windows interface reference

The target is the **Cubase Pro 15.0.30 Windows interface**, as requested by the user. The earlier Rebase Windows host passed bounded functional checks but its default white controls, oversized borders and clipped arrangement did not meet that visual target. Rebase's Mac interface is not the Windows reference.

## Static reference

The [official operation manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), retrieved 2026-10-23, identifies its screenshots as Windows captures on page 12. The inspected project window is on page 54, the platform menu distinction on page 55, the integrated transport on page 306, and the lower-zone mixer on page 435. The retained local PDF is 35,997,340 bytes, SHA-256 `59760cfc92d9c165cd0b2e7cad9c78f4dc9b04be4d70c11e77b0ff76126235b2`.

The reference uses compact top tool/status/info rows, separate channel and inspector areas, a track list beside the event display, a dense lower-zone console, and transport along the bottom. Mixer strips place pan above vertical faders and channel labels at the bottom. Windows supplies the application menu inside the project window.

Vendor screenshots and the PDF are study inputs outside this repository. Application controls and drawing code are independently authored. No proprietary executable was run. The manual establishes documented layout and visible states; it does not establish measured event timing, undocumented behavior, every customization, or pixel-identical runtime rendering.

## Verified preview and remaining work

[Native run 39939758507](../../research/publication/windows-portability/application-run-39939758507/observation.json) passed 39 actual-window checks at commit `6a6f4d4077fd817574d7f2756e3f060d693f35b5`. Its three 1084 × 749 client-area images were inspected independently and accepted for the scoped development preview. The earlier [run 39936173813](../../research/publication/windows-portability/application-run-39936173813/observation.json) remains unchanged, including its observed source-selector/header and capture-bounds defects.

| Journey | Current implementation and evidence | Remaining acceptance |
| --- | --- | --- |
| Open the bundled beat and select a track/clip | Native selection, move, undo/redo, Save As, reopen and render checks passed. The example opens as an editable copy. | Physical pointer/keyboard input and native file dialogs. |
| Read and edit audio events | Shared source-domain waveforms display all 11 clips and four rows. Independent helper checks verify 17,600 peak bins. Native geometry confirms four fixed headers and a 358-pixel event scroll. | Wider zoom/resize, editing and selection journeys; additional reference tool behavior. |
| Mix levels and pan | Inspector volume/pan/M/S and channel-strip volume/M/S use shared commands and history. Native automation verifies edits, inspector synchronization, focus restoration and undo. | Physical gestures, broader keyboard coverage, detailed reference fader scales, separate Channel area, routing and metering behavior. |
| Read musical time | Mac and Windows use the same tempo/signature display projection. Native labels put bar 2 at 2.5 seconds for the authored 96 BPM example; the seconds toggle passes. | Reference-customized ruler configurations and further timing modes. |
| Attach and audition a preserved source event | Shared strict PCM24 snapshot, native selection/attachment/undo/redo/export and exact provenance checks pass. Source selector and selected-event header now display correct text. | Actual audio output, other native audition modes and full imported-project behavior. |
| Publish a Windows build | Native package passes the mandatory optimized shared-test gate, runtime dependency closure and application checks. | Interactive Windows 11 and real audio-device verification; full feature parity. |

The preview follows the reference's compact top rows, neutral graphite event display, left inspector, lower channel strips and bottom transport. It is not an exact visual reconstruction. Toolbar tools remain text-heavy; the event information row, Channel/Inspector balance, mixer scales, right zone and many reference controls still differ or are absent. Those differences remain development work, not accepted equivalence.

The musical ruler is shared application display policy, not a claim about undocumented reference UI rounding. No source events become resolved merely because the ruler can display their timing.

Compare each subsequent actual Windows build with the reference at a recorded size. A WPF visual-tree PNG does not validate the operating-system title bar, physical input, native file dialogs, or human comprehension. Keep those limits alongside the result.
