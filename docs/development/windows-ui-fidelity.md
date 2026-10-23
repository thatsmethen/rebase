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


## Channel and compact-control follow-up

The follow-up adds a separate selected Channel strip and colored Inspector plate, synchronized track-header selection, a compact vector toolbar, and Enter/Escape event/tempo/position fields. The Channel and lower mixer share command/history behavior. The gain value can also be typed directly.

The old manually spaced fader labels were incorrect for the existing slider. Each tick now derives from the actual WPF Track/Thumb geometry and current linear-dB mapping. It does not substitute an unmeasured reference taper. Native smoke compares tick and thumb coordinates at -96, 0 and +24 dB in both fader sizes, and exercises Channel synchronization plus numeric commit/reject/cancel journeys.

[Native run 39946278931](../../research/publication/windows-portability/application-run-39946278931/observation.json) passed 54 window checks, 91 host controls and 52 packaged-helper checks. Both fader sizes align their ticks and actual thumbs at all three observed values to well below 0.5 DIP. All 13 [component jobs](../../research/publication/windows-portability/run-39946279018/observation.json) passed.

Those captures showed the separate Channel/Inspector, compact controls and synchronized selection. Root image review also found the selected Channel strip centered inside its stretched outer border, leaving unused space below its nameplate. The correction explicitly anchors that border to the bottom and adds a native nameplate-alignment gate.

[Native run 39949650116](../../research/publication/windows-portability/application-run-39949650116/observation.json) subsequently passed 55 window checks. The selected Channel nameplate bottom is 686 DIP and the lower mixer is 685.5 DIP. Independent inspection of all three fresh captures confirmed the gap is corrected, with the source journey and fixed-header scrolling retained. All 13 [component jobs](../../research/publication/windows-portability/run-39949650135/observation.json) also passed. This accepts the scoped Channel/toolbar refinement; it does not establish complete reference fidelity.


## Next visual acceptance work

The Windows reference remains the whole-window target. Inspection of the retained reference project-window image against the current arrangement shows three substantial gaps:

1. **Workspace density and sizing.** The current left panels have fixed widths, track rows are 68 DIP tall, and the lower mixer has a fixed height. Add bounded splitters and compact/normal track heights, while keeping the shared ruler and fixed track headers aligned. Verify selection, trim hit targets, scrolling and focus at smaller window sizes.
2. **Mixer and Inspector density.** Reuse the working gain, pan, mute, solo and selection commands in narrower strips and collapsible Inspector sections. Verify that the track header, Inspector, selected Channel and lower mixer remain synchronized through edits and undo.
3. **Top rows and event information.** Tighten the toolbar, status and event-info rows without losing readable fields, command access or Enter/Escape behavior. Keep the empty-selection state compact.

Routing, inserts, record/monitor state, automation read/write, per-channel meters, marker/arranger tracks, Control Room and cycle/locator behavior still need implementation. Their absence is a functional fidelity gap as well as a visual one. New surfaces require working shared behavior and interaction checks; the reviewed CPR import milestone does not satisfy these UI acceptance criteria.


## Compact workspace candidate

The next source candidate adds Compact (44 DIP) and Normal (68 DIP) track rows, left-zone and mixer visibility controls, a bounded lower-zone splitter, narrower mixer strips with resizing faders, and expandable Event editing/source sections. These change presentation only. Selection, history and shared project state must stay unchanged through density and pane changes. Ordinary clip actions are disabled for a retained source-only selection; choosing a new retained event expands its source section.

The [local readiness record](../../research/publication/windows-portability/workspace-local-20261024/observation.json) records a successful WPF Release crossbuild and 57 authored receipt-gate controls. These are not Windows runtime or visual acceptance. The native scenario adds 12 checks, two additional client images, measured rows/hit areas, pane transitions, splitter/fader geometry and session-state hashes. Windows execution and independent review are pending. Preview 3 remains the published tested download until that candidate passes its own review.

The top row heights are unchanged in this slice. Further toolbar density, panel sizing, reference control behavior and the functional gaps listed above remain open.
