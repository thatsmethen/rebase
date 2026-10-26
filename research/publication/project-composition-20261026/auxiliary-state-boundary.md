# Bounded auxiliary state consumption

After the common resource declaration and FSubList corrections, actual template inline dictionaries required four additional structural encodings before the top-level candidates could be inspected completely. These encodings are retained as uninterpreted auxiliary state; their contents do not become signal-processing claims.

- Subtype2 dispatch `1031abc50` reads a count and signed64 elements; subtype3 `1031abcb0` reads a count and binary64 elements.
- Subtype4 dispatch `1031ab7a0` creates the counted string list and reads each element through the native string reader `103109ff0` at `1031ab860`. The existing sealed audio-native string finding supplies that bounded ASCII/marked-UTF8 reader domain. Other legacy encodings remain unsupported.
- Subtype5 dispatch `1031abd10` is the FSubList domain documented in the explicit Child Bus correction.
- Subtype7 dispatch `1031abe44` reads a byte count and constructs a memory stream through `103181d4c`. That constructor installs primary table `104e438c8`; its +e8 slot is `103182948`. The memory source fast path copies at most the available declared byte count and advances the input; the generic fallback `103170c8c` reads/writes 1024-byte chunks then the remainder. The decoder requires the entire declared span within the bounded resource and never invokes or interprets the plugin payload.

The fresh constructor/reader/generic-copy functions and raw readbacks are retained in passes27–29. `verification-binary-state-01.json` verifies all 100 functions/readbacks against the original pinned image. `binary-state-reader-anchor.json` records the exact virtual slot. Earlier generic subtype7 rejection observations remain intact. The source tests now use still-unverified subtype9 for their opaque-unknown control; this is an explicit admitted-domain extension, not deletion of the rejection scenario.

Numeric/string arrays consume a shared bounded item budget. Binary lengths must fit the already size-limited original resource, and no partial-prefix candidate is published when structural parsing fails. An auxiliary array or blob cannot stand in for a scalar saved selector, Volume or bus dictionary. These tests do not establish runtime plugin or routing behavior.
