# WezTerm Image Panel

Show images from a local Codex CLI session in a WezTerm side pane or separate
window. Browse earlier images while Codex continues, or follow new images.

[中文教程](docs/使用教程.md) · [Validation](docs/validation.md) ·
[Privacy](docs/privacy.md) · [Scope](docs/scope.md)

Independent community tool. Requires **Python 3.9+** and
[WezTerm](https://wezterm.org/). The runtime has no third-party Python dependencies
and needs no separate OpenAI API key.

## Install

From a checkout, create a virtual environment and install the package.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m wezterm_image_panel --version
```

macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m wezterm_image_panel --version
```

Some Windows Python distributions create `.venv/bin/python.exe` instead of
`Scripts/python.exe`; use the path actually created. Activate the environment
to run `wezterm-image-panel`, or use its Python with `-m wezterm_image_panel`.
These are the two supported entry points. Source code lives under `src/` and
must be installed before use.

## Open a panel

In a **shell pane**, list your local sessions and choose the intended ID:

```sh
wezterm-image-panel sessions --limit 10
wezterm-image-panel open --session YOUR_SESSION_ID
```

`open` splits the invoking WezTerm pane. To place it beside a Codex pane from a
separate shell, find the Codex pane ID with `wezterm cli list` and pass it:

```sh
wezterm-image-panel open --session YOUR_SESSION_ID --pane-id 123
```

For an independent window, append `--standalone`. You can select a log directly
with `--rollout /path/to/session.jsonl`; `CODEX_HOME` and `--sessions-dir` control
session discovery. The newest session is not proof of the active conversation.

## Toggle from the Codex pane

Merge the binding from [examples/wezterm.lua](examples/wezterm.lua) into your
existing WezTerm configuration. Set `root` to the checkout directory, and install
its `.venv` as above:

```lua
local root = '/path/to/wezterm-image-panel'
local panel = dofile(root .. '/integrations/wezterm.lua')
table.insert(config.keys, {
  key = 'I', mods = 'CTRL|SHIFT', -- macOS: CMD|SHIFT
  action = panel.action { root = root },
})
```

Focus the **Codex pane**, then press **Ctrl + Shift + I** on Windows or
**Command + Shift + I** on macOS. Press again to close the preview. If the
session cannot be identified uniquely, select one from the preview's list.
A project-only title requires confirmation even with a single candidate.

`root` locates the checkout's virtual environment, including the Windows `bin`
variant. For another environment, pass an explicit argument array:
`command = { '/path/to/python', '-m', 'wezterm_image_panel' }`. With neither
option, the integration runs `wezterm-image-panel` from WezTerm's PATH.
No installer modifies your terminal configuration automatically.

## Viewer keys

Click the preview before using these keys:

| Key | Action |
| --- | --- |
| Left / H / K | Previous image; pause following |
| Right / J | Next image; pause following |
| Space / L | Toggle follow mode; resuming selects the latest image |
| O | Open the cached image in the system viewer |
| Q | Close the preview; keep Codex running |

A panel stays bound to its selected session. Close and reopen it after switching
Codex conversations.

## Offline demo and diagnostics

```sh
python examples/create_demo_session.py
wezterm-image-panel open --rollout .codex-local/demo/rollout-demo-session.jsonl --standalone
wezterm-image-panel doctor
wezterm-image-panel inspect --session YOUR_SESSION_ID
```

The demo generates three original geometric cards without personal logs. See
[the demo guide](docs/demo.md) for incremental image arrivals.

## Compatibility and privacy

Native Windows rendering commands, navigation, updates, resize, and side-pane
callbacks have been exercised with WezTerm and Codex CLI 0.163.0. Visual pixel
inspection and physical shortcut presses remain manual checks. Earlier macOS
GUI validation has not been rerun for this refactor; Linux/WSL viewing is
unvalidated. [Validation details](docs/validation.md) distinguish those results
from the hosted headless tests.

PNG, JPEG, GIF, and WebP are accepted up to 32 MiB each; terminal animation is
not guaranteed. The gallery reads one selected JSONL, including inline/MCP
images and supported direct `view_image` references. It does not merge older
pages, download remote URLs, or upload images. Codex log/index formats are
internal details and may change. Claude Code has no adapter in this release.

Snapshots stay in the local platform cache, overridable with `--cache-dir`.
They can outlive the original images; there is no automatic eviction. Logs,
screenshots, session IDs, and paths can be sensitive. Keep them in ignored
`.codex-local/` and use synthetic data for public reports.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/check_release.py
python -m pip install build
python -m build
python scripts/check_distributions.py
```

Runtime code is in `src/wezterm_image_panel/`, tests in `tests/`, release tools
in `scripts/`, and terminal integration in `integrations/`. The CLI and terminal
integration both launch the installed package. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the layout and commit rules.

[MIT license](LICENSE) · [Publishing notes](docs/publishing.md)
