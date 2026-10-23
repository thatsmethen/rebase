# Verified draft upload

The native application was already built and independently audited at `8c6ec4b`. A local upload stopped with HTTP 408 after 8,257,536 bytes. GitHub subsequently exposed an incomplete `starter` asset; [the retained metadata](failed-local-upload.json) identifies that exact draft asset and its removal. Completed release assets were retained.

The first [runner attempt](https://github.com/thatsmethen/rebase/actions/runs/39954574761) refused the incomplete asset without replacing it. Its [raw receipt](run-39954574761.json) remains failed. After the incomplete asset was removed, the [second attempt](https://github.com/thatsmethen/rebase/actions/runs/39955191121) uploaded the audited ZIP and confirmed its server digest. Its [raw receipt](run-39955191121.json) describes a draft at that time; the separate [publication record](../release-v0.21.1-windows-preview.2.json) verifies the later public release.

The helper validates successful workflow identity, source commit, recorded build gates, downloaded ZIP size/hash, exact draft target and resolved existing tag. It refuses incomplete/different assets and confirms an uncertain upload through server metadata. It does not execute the packaged app or publish a release.

The byte-exact [control script](controls.py) exercises 66 no-network cases, including malformed input, mismatched builds/releases/tags, altered ZIPs, no replacement, idempotence and a client timeout after successful server upload. [The original receipt](controls.json) binds both source hashes and the Python version. Run from the repository root:

```sh
python3 research/publication/windows-portability/release-upload-controls-20261023/controls.py
```

These controls validate the upload helper's decisions. The actual successful GitHub runner and subsequent public verification are separate observations. The earlier `target_commitish`-only helper was strengthened to resolve existing lightweight or annotated tags; the actual new preview tag was independently verified absent before publication.
