# Authored long-timeline controls

These three new structural fixtures place 512-frame stereo media beyond the old 32-million-frame Windows snapshot limit and near the shared timeline reader's 24-hour boundary. The overlap case retains a fully covered contributor and a higher-priority middle event that splits and restores the winning tail.

They were created by `SharedCPRAudioTests/CPRLongTimelineFixtureTests.swift`, using the existing `CPRAuditionModesControl.swift` archive builder. They are forward-authored implementation controls, not captured proprietary projects, native-valid examples or observations of reference audio. Project attachment UUIDs are generated; the exact checked-in bytes, source/report/project hashes, output counts and final 1000-frame PCM hashes are locked in `expected.json`. Regeneration creates a new destination and must never replace these records.

The tiny source media separates output duration from input storage. Complete long output must be drained incrementally; tail and EOF probes seek directly without allocating the leading silence. The ordinary snapshot exporter may still reject these timelines. The shared source admission limits remain separate from streaming queue and transport limits.

These fixtures are test inputs and must not be included in application release packages.
