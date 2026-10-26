# Saved Project Structure

The shared decoder now exposes preserved CPR project structure in both applications. This is development work following Windows preview 9; that released ZIP does not contain the inspector. Native Windows acceptance of this integration remains pending.

On macOS, use **File → Saved Project Structure**. On Windows, use **Project → Saved Project Structure**. The read-only view includes counted hierarchy order, typed audio-resource bindings, unresolved conditions and the complete JSON report. It describes the preserved source, including null, repeated and unknown objects, rather than subsequent Rebase edits. The existing historical import report and original CPR remain unchanged.

Saved provider/tag/index, raw Volume bits and bus identifiers remain source observations. The inspector does not apply them as gain, routing or mixer state. The [research continuation](../../research/publication/project-composition-20261026/README.md) separates the implemented binding decoder from subsequent output-registry and route-application findings.

## Complete report and custody

The snapshot revalidates the project manifest, preserved source and replayable historical import report. It binds the exact manifest and import-report bytes for its lifetime. A valid but differently serialized import report invalidates the pending snapshot too. The complete sorted JSON is limited to 8 MiB; larger reports fail explicitly instead of displaying a truncated result.

Windows reads 65,536-byte pages under a revision-bound token, verifies page identity, exact offsets, total length, SHA-256 and the typed report, then closes the token before showing the window. UTF-8 is decoded only after all bytes have been joined. Inspection preserves the document, selection, dirty state and undo history. A failed or stale read is not accepted as a complete report.

macOS uses the same snapshot directly. A separate document generation invalidates pending or displayed inspections when the project is replaced, edited or saved. Reopening an identical project or editing and then undoing still invalidates the earlier request. A late completion cannot clear the busy state or publish an error for a newer request.

## Validation boundary

Shared authored tests cover counted structure, declaration chronology, raw numeric state, paging, stale tokens, external changes, complete JSON and oversized refusal. Windows managed controls exercise the actual helper protocol and failure cases. Native window checks cover the real menu, all sections, read-only text, small-window geometry, a multi-page report, scrolling to its end and a dirty-edit/inspection/Undo journey. Their source is committed so Windows CI can execute them; cross-compilation or authored receipt tests alone do not establish native success.

The fixture generator creates deterministic, forward-authored packages separately from the downloadable application. It uses a historical interpretation profile solely to exercise preserved-report replay and the new structural decoder. These fixtures do not establish that the reference program accepts them. Private templates and the proprietary runtime are excluded from the package.

This inspector advances project understanding. Full project playback still requires effective output routing, processing state, automation, channel layout, activation and accumulation semantics; inspecting saved values does not satisfy those requirements.
