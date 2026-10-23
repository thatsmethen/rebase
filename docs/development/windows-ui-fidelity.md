# Windows interface reference

The target is the **Cubase Pro 15.0.30 Windows interface**, as requested by the user. The earlier Rebase Windows host passed bounded functional checks but its default white controls, oversized borders and clipped arrangement did not meet that visual target. Rebase's Mac interface is not the Windows reference.

## Static reference

The [official operation manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), retrieved 2026-10-23, identifies its screenshots as Windows captures on page 12. The inspected project window is on page 54, the platform menu distinction on page 55, the integrated transport on page 306, and the lower-zone mixer on page 435. The retained local PDF is 35,997,340 bytes, SHA-256 `59760cfc92d9c165cd0b2e7cad9c78f4dc9b04be4d70c11e77b0ff76126235b2`.

The reference uses compact top tool/status/info rows, separate channel and inspector areas, a track list beside the event display, a dense lower-zone console, and transport along the bottom. Mixer strips place pan above vertical faders and channel labels at the bottom. Windows supplies the application menu inside the project window.

Vendor screenshots and the PDF are study inputs outside this repository. Application controls and drawing code are independently authored. No proprietary executable was run. The manual establishes documented layout and visible states; it does not establish measured event timing, undocumented behavior, every customization, or pixel-identical runtime rendering.

## Current verification queue

| Journey | Implementation and evidence | Remaining acceptance |
| --- | --- | --- |
| Open the bundled beat and select a track/clip | Native run 39936173813 passed selection, move, undo/redo, Save As, reopen and render through the actual window. | Physical input, keyboard focus and selected-state review after follow-up changes. |
| Read and edit audio events | Source-domain waveform reducer is shared with macOS; native window displayed all 11 waveforms and all four rows. Process checks independently verified 17,600 peak bins. | Fixed headers during horizontal scrolling, zoom/resize and hover styling. |
| Mix levels and pan | Shared edit history and audio renderer remain authoritative; native capture shows dense channel strips. | Editable inspector volume/pan and M/S; native slider/keyboard behavior, focus retention, undo and selected-channel feedback. |
| Read musical time | macOS already uses the shared tempo/signature models for ruler positions. | Extract that display projection for Windows and verify its bars/beats against the authored example. |
| Attach and audition a preserved source event | Shared strict PCM24 source snapshot passed authored portable/private Mac regressions. Native window selection, attachment, undo/redo, export and exact provenance checks passed. | Correct the observed source selector object string and incorrect None header; audio hardware remains separate. |
| Publish a Windows build | Native run 39936173813 passed runtime closure, actual-window checks and the test gate. | Follow-up visual acceptance and fresh package audit; this intermediate ZIP is not a release. |

The [retained native images](../../research/publication/windows-portability/application-run-39936173813/observation.json) were reviewed at their recorded 1100 × 788 pixel size. They show readable waveform events and four visible track rows, but also expose the source-selector/header defects above. The capture used outer-window bounds for a client visual, leaving unused pixels corresponding to the nonclient frame; the follow-up should record and render actual client bounds. Passing functional smoke did not override these visual findings.

After implementation, compare the actual Windows window with the reference at a recorded size. A WPF visual-tree PNG does not validate the operating-system title bar, physical input, native file dialogs, or human comprehension. Record those limits alongside the result rather than treating a passing image or component test as full interface parity.
