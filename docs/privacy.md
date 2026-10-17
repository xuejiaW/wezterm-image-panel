# Privacy boundaries

## What the tool reads

The gallery reads the session log you select. Supported image records can
contain inline bytes, standard MCP image output, or local paths from direct
`view_image` calls. Paths from those calls are read after the matching
completion is observed. Use trusted local logs.

The `sessions` command lists metadata from recent local logs when requested.
Automatic identification inspects a local process and a read-only Codex SQLite
index. It can display candidate session names and working directories when a
choice is required. It does not choose a session merely because it is newest.
Windows process inspection reads IDs, parent IDs, and executable names through
PowerShell/CIM; it does not request command lines or process environments.

## What it writes

Images are copied to a local content-addressed cache. On POSIX hosts, newly
created cache directories and files request private permissions. Cached images
can outlive their original files; hashes are identifiers, not encryption. Close
panels before removing their cache to reclaim the space.
On Windows, cache access inherits the parent directory's account permissions;
POSIX mode bits do not establish Windows ACLs.

The opt-in development state file and commands such as `inspect`, `identify`,
and `doctor` can reveal local paths and runtime details. They are diagnostics,
not automatically sanitized public reports.

No image upload, analytics, remote URL fetch, or execution of commands from
session content is implemented. WezTerm and the system image viewer are invoked
as local subprocesses.

## Public repository boundary

- Keep real logs, SQLite databases, recordings, diagnostics, and original local
  material under ignored `.codex-local/`.
- Do not force-add ignored files. Ignore rules do not remove files already in
  Git history.
- Use [the synthetic demo](demo.md) for bug reports and public media.
- Run `python scripts/check_release.py` before committing or building.
- Check both Git contents and distribution archives. A clean working tree alone
  does not prove an older repository history is clean.

The release check catches selected file types, credential patterns, machine
home paths, and UUID-shaped identifiers. It is a guardrail, not a comprehensive
secret scanner or a substitute for reviewing image contents.
