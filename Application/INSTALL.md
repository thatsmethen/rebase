# Install Rebase 0.21.1

Requires an Apple silicon Mac (arm64) running macOS 14 or later. This experimental build is ad hoc signed, without an Apple Developer ID signature or notarization.

1. Download `Rebase-0.21.1-macos-arm64.zip` from the GitHub release assets. The automatically generated source archives do not contain the application.
2. Open the ZIP and drag `Rebase.app` to Applications.
3. Open Rebase. If macOS blocks it because the developer cannot be verified, review the download source, then follow Apple's [instructions for opening an app from an unidentified developer](https://support.apple.com/en-au/102445): System Settings → Privacy & Security → Open Anyway.

To verify the download, place the release's `SHA256SUMS` beside the ZIP and run `shasum -a 256 -c SHA256SUMS` in that folder.

Rebase supports bounded project import and source-audio audition; it does not provide full project fidelity. Keep original project files and media backed up. Third-party notices, SoXR source and its replacement instructions are included inside the app at `Contents/Resources/ThirdParty` and `Contents/Resources/ThirdPartyNotices.txt`.

Choose **File → Open Example Beat** (or the button on an empty project), then press Space to play the bundled four-track session. Edit the example and use Save to keep a copy in your chosen location.
