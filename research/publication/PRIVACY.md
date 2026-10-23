# Privacy and research publication

This publication keeps the application, research instruments, findings, protocols, analytical controls and compact validation records available for review and collaboration.

Local home and per-user temporary paths, personal author details, personal namespaces and unrelated account links have been replaced. Commit authors and committers use a generic project identity. Six raw accessibility or process captures were omitted because they contained local filesystem or process details. The original private archive is preserved separately.

The research export manifest identifies every included record. `original_sha256` and `original_bytes` refer to the private original; `sha256` and `bytes` refer to the distributed copy. `publication_transform` distinguishes unchanged records from privacy-redacted derivatives. Run `python3 research/publication/verify_research_export.py` to verify distributed bytes. Historical nested hashes and seals remain provenance for the private originals and cannot be revalidated solely from this public subset.

Technical identities such as native addresses, fixture UUIDs, scientific measurements and reference-build hashes are retained. Third-party authors and license notices are retained. Redacted local paths are illustrative placeholders; research scripts that used those paths require local configuration and their recorded private inputs.

The GitHub repository owner and contributors who choose to participate are publicly visible. Publication checks cover the distributed files, reachable Git history and release archive; they cannot establish that previously public copies were never downloaded or cached. The withheld repository history is not part of this publication.
