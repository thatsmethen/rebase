# Working in Rebase

Use this checkout and the existing GitHub repository for macOS, Windows, shared code and research. Do not create sibling repositories, worktrees or source checkouts unless the user explicitly requests one. Parallel contributors share this checkout and coordinate file ownership.

Keep task-specific local data inside the ignored `.local/` directory: `work/` for scratch data and downloaded CI artifacts, `tools/` for local instruments, `fixtures/` for the active private fixture view, `archives/` for preserved older work, and `builds/` for generated release staging. Normal application build caches remain under `Application/`. Never force-add `.local/`. Do not relocate system-managed tool caches solely to follow this convention.

Preserve original research records, failed observations, manifests and hashes. Historical absolute paths are evidence, not instructions to recreate old workspaces. Adapt active instruments or fixture links; add corrections rather than rewriting sealed records. Publish only reviewed research derivatives and accurately scoped results.

Keep the existing public repository and releases available. Do not change visibility, clear the repository, rewrite history or force-push unless the user explicitly requests that action again. Use normal commits and pushes. Avoid printing credential configuration or expanded Git remote URLs.
