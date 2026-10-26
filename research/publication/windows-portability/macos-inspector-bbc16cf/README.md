# macOS saved-structure Release verification

The native arm64 Release application was built from `bbc16cf2d19fc1e7cf31bd8edec816d99b7fc50a`. All 116 source inputs remained unchanged during the build. The archive was verified after extraction, including its ad-hoc signature, bundled example, icon, third-party notices and file-only metadata policy. The internal version remains 0.21.1, build 22; the new release tag identifies this development milestone.

The actual Release app opened the authored small project through File → Open Project and File → Saved Project Structure. All five sections were reached. Its complete JSON matched all 10,681 expected bytes, the final closing brace was visible, and a mute edit survived inspection and remained undoable after closing. All three preserved project files retained their original hashes.

The PNGs are unmodified captures of this Release app. The machine-local build logs and accessibility observations remain private with their hashes listed in the manifest. This visual run covers the authored small package; large-report protocol and Windows UI evidence are recorded separately. The application was not notarized. No proprietary reference was executed, and this work does not establish whole-project playback, effective routing or cross-platform feature parity.
