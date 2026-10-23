# Windows interface reference

The target is the **Cubase Pro 15.0.30 Windows interface**, as requested by the user. The earlier Rebase Windows host passed bounded functional checks but its default white controls, oversized borders and clipped arrangement did not meet that visual target. Rebase's Mac interface is not the Windows reference.

## Static reference

The [official operation manual](https://www.steinberg.help/api/khub/documents/O4PvzgK5U8lOyn4ANi_gKg/content), retrieved 2026-10-23, identifies its screenshots as Windows captures on page 12. The inspected project window is on page 54, the platform menu distinction on page 55, the integrated transport on page 306, and the lower-zone mixer on page 435. The retained local PDF is 35,997,340 bytes, SHA-256 `59760cfc92d9c165cd0b2e7cad9c78f4dc9b04be4d70c11e77b0ff76126235b2`.

The reference uses compact top tool/status/info rows, separate channel and inspector areas, a track list beside the event display, a dense lower-zone console, and transport along the bottom. Mixer strips place pan above vertical faders and channel labels at the bottom. Windows supplies the application menu inside the project window.

Vendor screenshots and the PDF are study inputs outside this repository. Application controls and drawing code are independently authored. No proprietary executable was run. The manual establishes documented layout and visible states; it does not establish measured event timing, undocumented behavior, every customization, or pixel-identical runtime rendering.

## Current verification queue

| Journey | Implementation and evidence | Remaining acceptance |
| --- | --- | --- |
| Open the bundled beat and select a track/clip | Shared document/session path and existing native-window smoke passed before the redesign. | New native capture, default-size visibility, keyboard focus and selected-state review. |
| Read and edit audio events | Source-domain waveform reducer is shared with macOS; boundary, offset, channel and chunk controls pass locally. | Real Windows waveform replies and image, move/trim/undo refresh, resize and scroll. |
| Mix levels and pan | Shared edit history and audio renderer remain authoritative; Windows controls are being restyled into strips. | Native slider/keyboard behavior, focus retention, undo and selected-channel feedback. |
| Attach and audition a preserved source event | Shared strict PCM24 source snapshot and provenance checks pass authored portable and focused private Mac regressions. | Native Windows source-selection/attachment/export smoke; audio hardware remains separate. |
| Publish a Windows build | The previous package passed runtime closure, actual-window checks, test gate and privacy scan. | Redesign acceptance and a fresh package; the rejected visual baseline is not a release. |

After implementation, compare the actual Windows window with the reference at a recorded size. A WPF visual-tree PNG does not validate the operating-system title bar, physical input, native file dialogs, or human comprehension. Record those limits alongside the result rather than treating a passing image or component test as full interface parity.
