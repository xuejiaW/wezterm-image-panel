# Scope

WezTerm Image Panel displays images from a selected local coding-agent session
in a WezTerm pane. WezTerm supplies the image renderer and pane controls.

The first supported session source is **Codex CLI**. The current implementation
reads its local JSONL records, optionally consults its SQLite index, snapshots
supported image bytes, and keeps a gallery bound to that selected session.
It targets native Windows and macOS; exact validation is in
[VALIDATION.md](validation.md).

The current workflow includes opening a side pane or independent window,
following new images, browsing earlier images, resizing, opening a cached image
externally, and closing the preview while Codex continues. Session ambiguity
requires a choice. Files and images stay on the local machine.

Claude Code or another CLI could be added through a separate session adapter
after inspecting its actual local image records and active-session identity.
Such an adapter is not implemented or tested in this version. A renderer for
another terminal would likewise require separate implementation and validation.

Remote session synchronization, image generation, editing, cloud storage, and
automatic installation into terminal configuration are outside the current
release scope. Codex log/index formats are internal details, so future versions
may need compatibility updates.
