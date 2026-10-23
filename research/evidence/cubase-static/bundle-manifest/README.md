# Cubase resource-manifest inventory

This is a static inventory of declarations in the recovered outer `CodeResources`, compared with the partial extraction ledger. It is not a complete application inventory, proof of licensed features, or verification of the outer application seal. No Cubase code or scripts were executed. This task produced only paths, hashes and metadata; it did not copy or display art assets.

The manifest is 432,919 bytes with SHA-256 `c7b8e3234e2efefb0c7aa2ddf815d413c69ac710460b6908ccdcfdf655ac2c8e`. Its `files2` table declares 2,204 paths. The older `files` table contains 56 of those same paths, so adding the table lengths would overcount. Rules omit some items, including the outer `Info.plist` and `PkgInfo`; declarations are not an exhaustive filesystem listing.

| Exclusive category | Declared paths | Complete files independently rehashed |
|---|---:|---:|
| Bundled VST3 plug-in paths | 863 | 51 |
| Resources and presets | 775 | 1 |
| Other component paths | 267 | 0 |
| Scripts and control definitions | 248 | 0 |
| Localization paths | 23 | 0 |
| External library paths | 14 | 0 |
| Framework paths | 12 | 0 |
| Nested native libraries | 2 | 2 |
| **Total** | **2,204** | **54** |

Categories are exclusive: framework and localization paths are separated before grouping by top-level directory. The raw top-level counts are also recorded in `findings.json`; those are another view of the same entries and should not be added to this table.

The VST3 declarations span eight named bundles, which is not a plug-in class count. The Components directory has 285 declared paths before framework/localization separation: 29 `.bundle` or `.app` groups, an audiocodecs group, and two scanner paths. Framework declarations describe two REX framework locations, with 12 paths including symlinks. Fifteen `.lproj` directory locations account for 23 localization paths. The script/control group comprises 154 patch-name `.txt` paths and 94 MIDI Remote paths; the directory label does not make all of these executable scripts. There are also 618 preset paths, already included within resources.

The acquisition ledger contains 85 complete cpio records: 28 directories and 57 written regular files. All 57 files were rehashed independently and match their ledger lengths and SHA-256 values. Fifty-four have explicit outer-manifest entries: 52 match declared raw SHA-256 hashes, while the two main graphics dylibs have `cdhash` and designated-requirement records. Those CodeDirectory hashes were not compared to raw file hashes. The other three acquired files are the outer manifest itself, the main executable, and a ModScripter AppleDouble metadata file. Ledger agreement is not signature verification or proof of uncorrupted original acquisition.

The remaining 2,150 declared paths have no complete recovered file in this ledger. This includes the VST Connect executable, whose partial bytes were never promoted to a component filename. All declared paths under LoopMash FX (26), ModScripter (17), and vstambiconverter (7) are present and hash-matched, but this alone does not verify those sealed bundles or establish host behavior.

REA's app-root request failed because the partial app lacks `Info.plist`; that error is retained. The successful request used the verified graphics dylib as a native inspection anchor and the manifest's absolute path. Evidence ID: `ev_9b0a59c78e5c74bc3be7ad77f3e02abc0563f199ff8f70045d14e718928d9f42`. Provider: `native-macos`. The REA subject digest identifies the anchor dylib, so the manifest digest is pinned independently above. The full normalized plist value was checked against Python's independent `plistlib` decode and matched. REA reports that `plutil` required XML conversion and typed binary-data values.

Useful next questions are bounded by acquisition status:

1. The acquired ModScripter documentation, module metadata and six example scripts can support explicit contract hypotheses and original test vectors. Host scheduling and execution semantics require separate evidence.
2. The declared MIDI Remote API types and example-controller paths may expose stable controller contracts once acquired; no content is currently available in this recovery set.
3. The declared logical-editor, input-transformer and key-command presets suggest format-validation and malformed-input experiments after acquisition.
4. Names such as DAWproject, AAFfilter and omffilter can prioritize later import/export round-trip studies; names alone do not establish implementation behavior.

`findings.json` is the concise machine-readable report. `path-inventory.json` retains every declaration, its provenance, availability and hash comparisons; `path-inventory.csv` is a compact index. `recovered-file-metadata.json` records all 57 rehashed files. `code-resources-plist.json` preserves the full local REA response. Reproduce the derivation from the project root with:

```sh
python3 research/evidence/cubase-static/bundle-manifest/derive_inventory.py
```

The script refuses an unexpected source digest, verifies the REA decoding against the source, and detects recovery-ledger changes during collection. It does not authenticate the manifest's enclosing application signature.
