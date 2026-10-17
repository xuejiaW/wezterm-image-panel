# WezTerm Image Panel

Browse images from a local Codex CLI session in a **WezTerm side pane** or a
separate preview window. Keep working in Codex while the panel follows new
images, or pause it to inspect an earlier one.

[中文使用教程](docs/使用教程.md) · [Privacy](docs/privacy.md) ·
[Validation](VALIDATION.md) · [Contributing](CONTRIBUTING.md)

Current scope: **WezTerm + local Codex CLI**, on native Windows and macOS.
See [scope and future adapters](docs/scope.md) for the project boundaries.

This is an independent community tool. It reads local session files; it does
not require an OpenAI API key, a Codex fork, or a HUD plugin.

## Features

- Display inline session images, standard MCP image results, and local images
  recorded by direct `view_image` calls.
- Follow the newest image, browse the gallery, and deduplicate identical bytes.
- Resize images to fit the preview pane without changing their aspect ratio.
- Toggle a side pane using an optional WezTerm key binding.
- Select the session explicitly when automatic identification is ambiguous.
- Run an offline demonstration with generated test cards and no personal logs.

## Requirements and compatibility

- Python **3.9+**; the runtime uses only the Python standard library.
- [WezTerm](https://wezterm.org/), including its `cli` and `imgcat` commands.
- A local Codex CLI session log containing image data or supported local image
  references. Automatic identification uses Codex's local SQLite index and
  process inspection (`ps`/`lsof` on macOS, PowerShell/CIM on Windows).

Native Windows rendering commands, navigation, and side-pane callbacks have
been exercised in actual WezTerm processes with Codex CLI 0.163.0. Desktop
screenshots and physical shortcut presses were not verified in that run.
Earlier macOS GUI validation has not been rerun; Linux/WSL viewing is
unvalidated. See the exact [validation boundaries](VALIDATION.md).

Codex's local log and index formats are implementation details, not a stable
public API. A future Codex update may require an adapter change. Explicit
`--rollout` selection avoids the automatic identification dependency, but still
depends on the log format.

## Install from a checkout

Open the project directory in a regular terminal, then create an isolated
environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
wezterm-image-panel --version
```

These commands are for macOS. On Windows, use PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m wezterm_image_panel --version
```

Use that Python executable with `-m wezterm_image_panel` in place of
`wezterm-image-panel` in the commands below, or activate the environment to use
the installed command. Some Python distributions use `bin` instead of `Scripts`;
use the interpreter path actually created by your distribution.

No program changes your WezTerm configuration automatically. The
`wezterm-image-panel` shell script is an additional macOS/Linux source entry
point. Windows can run `python wezterm_image_panel.py` directly from this checkout.

## Try it without personal data

From the checkout, with the environment activated:

```sh
python examples/create_demo_session.py
wezterm-image-panel inspect --rollout .codex-local/demo/rollout-demo-session.jsonl
wezterm-image-panel open --rollout .codex-local/demo/rollout-demo-session.jsonl --standalone
```

The generator creates three original geometric test cards in an ignored local
log. It does not read Codex configuration, sessions, credentials, or screenshots.
It refuses to overwrite an existing file.

For a live-arrival demonstration, create a new fixture using `--delay 5` in one
terminal and open that path from another. See [the demo guide](docs/demo.md).
The public source tree contains no recordings from personal Codex sessions.

## Open a real session

List local session IDs and their working directories:

```sh
wezterm-image-panel sessions --limit 10
```

Choose the exact session you intend to view. Multiple sessions can share a
working directory; the newest file is not proof that it is the active session.

```sh
wezterm-image-panel open --session YOUR_SESSION_ID --standalone
```

Inside WezTerm, split the current pane instead:

```sh
wezterm-image-panel open --session YOUR_SESSION_ID
```

To place the panel next to another pane, find its ID with `wezterm cli list`:

```sh
wezterm-image-panel open --session YOUR_SESSION_ID --pane-id 123 --percent 40
```

Replace both placeholders. If session discovery fails, pass the log directly:

```sh
wezterm-image-panel open --rollout /path/to/session.jsonl --standalone
```

Custom Codex homes are read from `CODEX_HOME`. You can also pass
`--sessions-dir /path/to/sessions` to session commands.

## Optional toggle shortcut

The supplied [WezTerm example](examples/wezterm.lua) binds **Ctrl + Shift + I**
on Windows and **Command + Shift + I** on macOS to open or close the panel beside
the focused Codex pane. Merge that binding
into your existing configuration; do not replace your entire config.

Set `root` to your checkout location and `command` to the executable in the
environment you created. The integration accepts an argument array, so paths
containing spaces work without shell quoting:

```lua
local panel = dofile(root .. '/wezterm_integration.lua')
local image_action = panel.action {
  command = { root .. '/.venv/bin/wezterm-image-panel' },
  size = 0.40,
}
-- Use image_action as the action of your preferred WezTerm key binding.
```

Set either `command` or `root`. With `{ root = root }`, the module runs
`python` on Windows or `python3` on other hosts against the source in that
directory. An explicit `command` is preferable when using a virtual environment.
There is no fixed checkout path. Automatic identification is for a local Codex
process; SSH sessions need an explicit accessible log instead. Project-only
terminal titles require a session selection, even if there is only one candidate.

## Viewer keys

| Key | Action |
| --- | --- |
| Left / H / K | Previous image; pause following |
| Right / J | Next image; pause following |
| Space / L | Toggle follow mode; resuming selects the latest image |
| O | Open the current cached image in the system image viewer |
| Q | Close the preview |

Click the preview pane before using these keys. Closing the preview leaves
the Codex process running. A panel remains bound to its selected session;
close and reopen it when switching to a different one.

## Image and privacy boundaries

PNG, JPEG, GIF, and WebP signatures are supported, up to **32 MiB per image**.
GIF input does not imply animated playback in the terminal. Plain text paths
and remote image URLs are not downloaded. A direct `view_image` reference is
snapshotted when its matching tool completion is observed.

The gallery reads only its selected log. The `sessions` command explicitly
lists metadata from recent logs. No command executes instructions from logs or
uploads images. Cached snapshots can remain after the original image changes.
There is no automatic cache eviction.
Older pages or archived logs are not automatically merged into the gallery.

- macOS cache: `~/Library/Caches/wezterm-image-panel`
- Windows cache: `%LOCALAPPDATA%\wezterm-image-panel` (inherits Windows account ACLs)
- Other hosts: the platform cache directory; `--cache-dir` overrides it.
- Local logs, captures, and diagnostics belong under ignored `.codex-local/`.

Diagnostic output and screenshots can expose paths, session IDs, and image
contents. Use synthetic fixtures for public issues and recordings. Read
[the privacy notes](docs/privacy.md) before sharing evidence.

## Troubleshooting

```sh
wezterm-image-panel doctor
wezterm-image-panel inspect --session YOUR_SESSION_ID
```

`inspect` reports the number of readable images and skipped records. If it
reports zero, verify the session and whether the image was actually stored
locally. If WezTerm's existing control interface times out, try `--standalone`.
If automatic identification cannot read the local index, use `--rollout`.

## Development

```sh
python -m unittest discover -v
python scripts/check_release.py
python -m pip install build
python -m build
python scripts/check_distributions.py
```

Tests use temporary synthetic files and mocked processes. They do not require
Codex, WezTerm, an API key, or access to real sessions. CI runs headless tests
on macOS, Linux, and Windows; it does not validate GUI rendering.

## License

[MIT](LICENSE). See [the publishing notes](docs/publishing.md) for the first
GitHub upload and commit identity setup.
