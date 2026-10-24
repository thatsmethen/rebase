# Windows interface reference

The target is the **Cubase Pro 15.0.30 Windows interface**, as requested by the user. The earlier Rebase Windows host passed bounded functional checks but its default white controls, oversized borders and clipped arrangement did not meet that visual target. Rebase's Mac interface is not the Windows reference.

## Static reference

The [official operation manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), retrieved 2026-10-23, identifies its screenshots as Windows captures on page 12. The inspected project window is on page 54, the platform menu distinction on page 55, the integrated transport on page 306, and the lower-zone mixer on page 435. The retained local PDF is 35,997,340 bytes, SHA-256 `59760cfc92d9c165cd0b2e7cad9c78f4dc9b04be4d70c11e77b0ff76126235b2`.

The reference uses compact top tool/status/info rows, separate channel and inspector areas, a track list beside the event display, a dense lower-zone console, and transport along the bottom. Mixer strips place pan above vertical faders and channel labels at the bottom. Windows supplies the application menu inside the project window.

Vendor screenshots and the PDF are study inputs in ignored local storage; they are excluded from published repository content. Application controls and drawing code are independently authored. No proprietary executable was run. The manual establishes documented layout and visible states; it does not establish measured event timing, undocumented behavior, every customization, or pixel-identical runtime rendering.

## Initial accepted preview

[Native run 39939758507](../../research/publication/windows-portability/application-run-39939758507/observation.json) passed 39 actual-window checks at commit `6a6f4d4077fd817574d7f2756e3f060d693f35b5`. Its three 1084 × 749 client-area images were inspected independently and accepted for the scoped development preview. The earlier [run 39936173813](../../research/publication/windows-portability/application-run-39936173813/observation.json) remains unchanged, including its observed source-selector/header and capture-bounds defects.

| Journey | Implementation at that milestone | Acceptance still required at that milestone |
| --- | --- | --- |
| Open the bundled beat and select a track/clip | Native selection, move, undo/redo, Save As, reopen and render checks passed. The example opens as an editable copy. | Physical pointer/keyboard input and native file dialogs. |
| Read and edit audio events | Shared source-domain waveforms display all 11 clips and four rows. Independent helper checks verify 17,600 peak bins. Native geometry confirms four fixed headers and a 358-pixel event scroll. | Wider zoom/resize, editing and selection journeys; additional reference tool behavior. |
| Mix levels and pan | Inspector volume/pan/M/S and channel-strip volume/M/S use shared commands and history. Native automation verifies edits, inspector synchronization, focus restoration and undo. | Physical gestures, broader keyboard coverage, detailed reference fader scales, separate Channel area, routing and metering behavior. |
| Read musical time | Mac and Windows use the same tempo/signature display projection. Native labels put bar 2 at 2.5 seconds for the authored 96 BPM example; the seconds toggle passes. | Reference-customized ruler configurations and further timing modes. |
| Attach and audition a preserved source event | Shared strict PCM24 snapshot, native selection/attachment/undo/redo/export and exact provenance checks pass. Source selector and selected-event header now display correct text. | Actual audio output, other native audition modes and full imported-project behavior. |
| Publish a Windows build | Native package passes the mandatory optimized shared-test gate, runtime dependency closure and application checks. | Interactive Windows 11 and real audio-device verification; full feature parity. |

That preview followed the reference's compact top rows, neutral graphite event display, left inspector, lower channel strips and bottom transport. It was not an exact visual reconstruction. The subsequent Channel, workspace and top-row milestones below address portions of its toolbar, event information, panel balance and mixer-scale gaps. Right-zone and other reference workflows remain incomplete.

The musical ruler is shared application display policy, not a claim about undocumented reference UI rounding. No source events become resolved merely because the ruler can display their timing.

Compare each subsequent actual Windows build with the reference at a recorded size. A WPF visual-tree PNG does not validate the operating-system title bar, physical input, native file dialogs, or human comprehension. Keep those limits alongside the result.


## Channel and compact-control follow-up

The follow-up adds a separate selected Channel strip and colored Inspector plate, synchronized track-header selection, a compact vector toolbar, and Enter/Escape event/tempo/position fields. The Channel and lower mixer share command/history behavior. The gain value can also be typed directly.

The old manually spaced fader labels were incorrect for the existing slider. Each tick now derives from the actual WPF Track/Thumb geometry and current linear-dB mapping. It does not substitute an unmeasured reference taper. Native smoke compares tick and thumb coordinates at -96, 0 and +24 dB in both fader sizes, and exercises Channel synchronization plus numeric commit/reject/cancel journeys.

[Native run 39946278931](../../research/publication/windows-portability/application-run-39946278931/observation.json) passed 54 window checks, 91 host controls and 52 packaged-helper checks. Both fader sizes align their ticks and actual thumbs at all three observed values to well below 0.5 DIP. All 13 [component jobs](../../research/publication/windows-portability/run-39946279018/observation.json) passed.

Those captures showed the separate Channel/Inspector, compact controls and synchronized selection. Root image review also found the selected Channel strip centered inside its stretched outer border, leaving unused space below its nameplate. The correction explicitly anchors that border to the bottom and adds a native nameplate-alignment gate.

[Native run 39949650116](../../research/publication/windows-portability/application-run-39949650116/observation.json) subsequently passed 55 window checks. The selected Channel nameplate bottom is 686 DIP and the lower mixer is 685.5 DIP. Independent inspection of all three fresh captures confirmed the gap is corrected, with the source journey and fixed-header scrolling retained. All 13 [component jobs](../../research/publication/windows-portability/run-39949650135/observation.json) also passed. This accepts the scoped Channel/toolbar refinement; it does not establish complete reference fidelity.


## Remaining reference fidelity

The Windows reference remains the whole-window target. The accepted milestones below now provide compact/normal rows, pane visibility and a bounded lower splitter, narrower mixer strips, collapsible Inspector sections and compact event information. The next substantial gaps are:

1. **Inline automation.** The selected-track editor provides real Volume/Pan editing, but the reference's arrangement automation lanes and their controls are not implemented. Write/touch/latch modes need shared behavior before working controls can be shown.
2. **Additional workspace layouts.** Channel/Inspector widths remain fixed, and the right zone is absent. Broader resize, zoom and physical-input journeys need interactive verification; the hosted wider-window request was constrained to 1100 DIP.
3. **Reference processing and transport controls.** Routing, inserts, record/monitor state, per-channel meters, marker/arranger tracks, Control Room and cycle/locator behavior remain missing. Each needs working shared behavior and interaction checks.

These are functional gaps as well as visual differences. Neither the reviewed CPR import nor the separate automation editor establishes exact reference fidelity.


## Compact workspace development record

The workspace candidate added Compact (44 DIP) and Normal (68 DIP) track rows, left-zone and mixer visibility controls, a bounded lower-zone splitter, narrower mixer strips with resizing faders, and expandable Event editing/source sections. These change presentation only. Selection, history and shared project state must stay unchanged through density and pane changes. Ordinary clip actions are disabled for a retained source-only selection; choosing a new retained event expands its source section.

The [local readiness record](../../research/publication/windows-portability/workspace-local-20261024/observation.json) records a successful WPF Release crossbuild and 57 authored receipt-gate controls. These are not Windows runtime or visual acceptance. The native scenario adds 12 checks, two additional client images, measured rows/hit areas, pane transitions, splitter/fader geometry and session-state hashes. At that point Windows execution and independent review were pending, and preview 3 remained the tested download. The later failed runs and accepted preview below preserve that sequence.

The top row heights are unchanged in this slice. Further toolbar density, panel sizing, reference control behavior and the functional gaps listed above remain open.

The first [native workspace run](../../research/publication/windows-portability/application-run-40011890840/observation.json) stopped at the Normal-density fit check after six checks. It recorded no viewport bounds or image, so the exact failed geometry is unknown. All 13 [component jobs](../../research/publication/windows-portability/run-40011890925/observation.json) passed separately. Source analysis found that the 246-DIP initial mixer can leave too little height for four 68-DIP rows after scrollbar allocation. The [correction](../../research/publication/windows-portability/workspace-local-20261024-02/observation.json) starts the mixer at 216 DIP, retains its resize limits and strict fit check, and retains incremental layout diagnostics and a failure image. That corrected source requires a separate native run.

The subsequent [native run 40015599492](../../research/publication/windows-portability/application-run-40015599492/observation.json) passed Normal sizing: its 327-DIP viewport contains the 298-DIP ruler and rows. It stopped after 63 checks at source-section auto-expansion. Source review established that the scenario selected the same track and event again, which preserves selection by design; it did not create the new-selection transition required by that assertion. The original timeout remains recorded.

This run also exposes a separate application defect. The timeline used its outer size minus a fixed nine pixels instead of the actual scroll viewport, producing eight DIP of unnecessary vertical scrolling and a 4.5-DIP content offset with panels hidden. Its five retained images and incremental geometry make those defects observable. All 13 [component jobs](../../research/publication/windows-portability/run-40015599436/observation.json) passed, but the failed native candidate has no distributable ZIP and is not released.

The [next correction](../../research/publication/windows-portability/workspace-local-20261024-03/summary.json) uses the measured content viewport, anchors the canvas and removes empty-row extent padding. Its source-selection scenario uses a separately identified scratch derivative with one empty track, verifies a real selection change, then restores the canonical fixture before attachment/export. The original source and report bytes are checked unchanged. The local Release crossbuild and 90 authored receipt-gate controls pass; the latter reject the observed geometry defects and invalid selection-transition evidence. These local results required a fresh Windows observation, subsequently recorded in the accepted workspace preview below.


## Accepted compact workspace preview

[Native run 40021483751](../../research/publication/windows-portability/application-run-40021483751/observation.json), exact source `6289343`, passed 80 window checks, 155 host controls and 91 packaged-helper checks. Its shared Release gate executed 90 tests with one explicit skip and no failures; all 13 [component jobs](../../research/publication/windows-portability/run-40021483798/observation.json) also passed. All eight workspace states have matching measured viewport/extent and zero unnecessary vertical scroll. Their session/selection hashes are unchanged. The separate source-selection control proves the intervening empty selection and restores the canonical fixture before attachment/export.

The [downloaded archive audit](../../research/publication/windows-portability/application-run-40021483751/candidate-review.json) verifies the exact package, manifest, bundled example and runtime closure. Seven native client images received root and independent review. [Preview 4](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.4) publishes that exact source and its images. This accepts the compact/normal rows, pane sizing and source-control slice, not full reference fidelity.

[Preview 5](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.5), exact source `5dd3beb`, completes the next measured slice: menu/toolbar/status/event rows total 107 DIP, unavailable source-event timing is explicit, long names retain tooltips, and row dividers extend across the visible canvas. [Native run 40033023717](../../research/publication/windows-portability/application-run-40033023717/observation.json) passed 87 window checks; the independent downloaded-package audit and root review cover all nine images. Its wider-window request remained constrained to 1100 DIP, leaving wider-desktop behavior unverified. The scrolled ruler-corner label is present; the earlier root reading was [corrected without altering the source image](../../research/publication/windows-portability/application-run-40021483751/root-visual-review-correction.json). Functional reference gaps and interactive Windows/device verification remain open.

## Top-row and event-information development record

The [local candidate](../../research/publication/windows-portability/top-rows-local-20261024/summary.json) reduces the top stack from 126 to 107 DIP, retains the existing commands, and aligns event labels and fields. Project identity and the retained-source playback limitation occupy separate bounded regions. Empty/source-only selections show unavailable ordinary timing; ordinary zero-valued events still show zero. Divider strokes now follow the resized canvas width.

The Release crossbuild passed with no warnings or errors. All 105 authored receipt-gate controls passed and reproduced byte exactly. Seven additional native checks cover measured text/control bounds, long-name ellipsis and full-name tooltips, empty/source timing guards, resized session preservation, divider width and ruler-corner anchoring. Two new client captures have their own bounds; a constrained requested width will not count as wider-window evidence. Those were local readiness results only. Native execution and image review subsequently passed in preview 5, as recorded above.

## Accepted automation editor

[Preview 6](https://github.com/thatsmethen/rebase/releases/tag/v0.21.1-windows-preview.6), exact source `32e6d37`, adds the selected-track Volume/Pan editor to the existing workspace. [Native run 40040015003](../../research/publication/windows-portability/application-run-40040015003/observation.json) passed 102 actual-window checks, 191 host controls and 169 packaged-helper checks. All 13 [component jobs](../../research/publication/windows-portability/run-40040015052/observation.json) passed, including shared edited/restored automation audio comparisons. The [independent package audit](../../research/publication/windows-portability/application-run-40040015003/candidate-review.json) and root review cover the downloaded package and all twelve client images.

The editor displays the actual shared points and outgoing Linear/Hold segments, accepts numeric or curve insertion, switches between Volume and Pan, and exposes per-lane Read. With Read off, points remain visible while the manual track value is used. Revision-bound edits and stale/invalid input checks preserve the document on failure. The native journey verifies point edits, parameter changes, deletion and undo/redo; undo restores the original locked WAV. Three 664 × 521 client images show the restored five-point Volume lane, retained invalid input with guidance, and the Read-off curve/manual baseline at the minimum editor size. Required fields, list viewport and footer actions remain inside the measured client.

Successful Windows edits enter shared undo history immediately and Close retains them. The Mac editor currently stages changes until Apply or Cancel. The Windows editor is a separate selected-track window, not an implementation of the reference's inline automation lanes or writing modes. Existing larger lanes are retained; the session limits growth to 4,096 points, and curves above 16,384 points explicitly report unavailable drawing while retaining list/numeric access.

These checks use automation peers, injected routed keys and a programmatically invoked production curve callback. Physical input, native dialogs, operating-system frames and audible device output remain unverified. The twelve images retain the existing 1100-DIP hosted width constraint. Full Mac parity and exact Windows reference fidelity remain open.

## Shared source-audio dialog

The [preview.8 native run](../../research/publication/windows-portability/application-run-40051952551/observation.json) adds a Source Audio window with eight shared modes, selected clock/duration and complete-track contributor metadata. Actual UI Automation exports match a separately invoked helper. Three 724 × 501 client captures show conversion, complete-track and unavailable states with the full mode list and footer. All fifteen native images were reviewed; the new dialog is an authored Rebase workflow and does not establish exact reference dialog fidelity. Physical input, native frame and hardware audio remain unverified.
