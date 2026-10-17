# Validation and support scope

## 0.4.1 package refactor — 2026-10-17

- 41 local automated tests passed after moving runtime code into `src/` and
  tests into `tests/`, including commit-message validation and explicit side-pane
  ownership. The moved parsing/rendering functions retain their original ASTs.
- The package installed into a fresh environment outside the checkout's module
  path. Version/help, synthetic image inspection, and the packaged standalone
  profile passed. Wheel and source archive privacy checks passed.
- The current local Codex conversation opened beside its source pane in native
  Windows WezTerm. Two images were parsed with zero errors and successful image
  rendering commands. User-specific configuration and diagnostics remain local.
- The WezTerm configuration loader accepted the Ctrl+Shift+I callback binding.
  A physical key press and pixel-level screenshot review remain manual checks.
- The original public CI run passed all seven platform/package jobs. The current
  workflow additionally checks new commit messages; it does not retroactively
  rename the original published commit.

## 0.4.0 preparation — 2026-10-17

Local environment: native Windows, Python 3.12.9, WezTerm
20260828-101755-27d55bef, and Codex CLI 0.163.0. The Python used locally was a
MinGW/UCRT distribution; its virtual environments use `bin`, whereas standard
Windows Python normally uses `Scripts`.

Observed checks:

- **36 automated tests passed**, covering synthetic session parsing, partial
  writes, deduplication, shared-cache writers, keyboard decoding, Windows process
  ancestry, Windows path variants, session ambiguity, CLI handling, and demo
  creation. Mocked tests do not require real sessions or an API key.
- The headless Lua check passed, including a context without the debug library,
  configurable commands, Windows interpreter selection, and closing only the
  owned preview.
- A real Codex `exec` session received an original synthetic image. A second
  real session used an image-viewing tool. The selected JSONL logs each yielded
  one distinct image with zero parse errors, including inline tool image output.
- Actual WezTerm processes ran the native Windows viewer and `imgcat`
  successfully. The panel reported successful rendering for the real session
  images. Screen text was checked through the WezTerm CLI.
- Input injected through the WezTerm CLI exercised previous/next, pausing, and
  following the latest image. A synthetic log grew from three to five images;
  paused navigation stayed on its selected image. Splitting and restoring the
  pane changed its reported width and successfully reran image rendering.
- A real Codex TUI resumed the synthetic session. A private harness invoked the
  same Lua callback used by the shortcut, opened a side pane, required an explicit
  session choice for the project-only title, rendered the selected session's
  image, and closed the preview while the source Codex process remained running.
  The pre-existing user panes were preserved.

The desktop tool did not provide a targetable WezTerm window, and its app-launch
request was blocked. No screenshot-based visual inspection was completed.
Successful `imgcat` execution and panel state are process-level evidence;
they do not prove every displayed pixel is correct. Physical shortcut presses
and the external image viewer (`O`) still need a manual check.

All session logs, test harnesses, raw state, and earlier personal recordings stay
under ignored `.codex-local/`. They are not public release assets. The public
demo generates original test cards without reading personal sessions.

## Platform matrix

| Capability | Status |
| --- | --- |
| Native Windows parser, viewer commands, input, live updates, resize | Exercised locally in actual WezTerm processes |
| Native Windows Codex session choice and side-pane callback | Exercised with a real local Codex TUI |
| Windows screenshot appearance, physical hotkey, external opener | Manual check pending |
| macOS image rendering and navigation | Earlier local GUI validation; current changes not rerun on macOS |
| Linux / WSL interactive viewing | Unvalidated |
| Claude Code or other session sources | Adapter not implemented |
| Other terminals | Renderer/integration not implemented |
| Future Codex local log/index formats | Compatibility not guaranteed |

## Repeatable checks

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
wezterm --config-file scripts/check_wezterm.lua show-keys --lua
python -m pip install build
python -m build
python scripts/check_distributions.py
```

The wheel and source distribution must pass the archive privacy check. Install
the wheel into a fresh environment, switch outside the source tree, and check
its version/help and inspection of the three-image synthetic demo. The GitHub
workflow runs headless tests on macOS, Linux, and Windows and builds both package
formats. Its hosted run remains pending until the repository is published.

## Manual checklist before a tagged release

1. Install from a fresh checkout into a new virtual environment.
2. Generate the [synthetic demo](demo.md), open it in WezTerm, and visually
   inspect the three images, aspect ratio, and footer at different pane sizes.
3. Press actual arrow/space keys and the configured open/close shortcut. Confirm
   the source Codex pane survives. Open an image externally with `O`.
4. Repeat on macOS to validate the current Lua and shared console changes.
5. Check one real session privately; never commit its logs, images, or reports.

This is ready to share as an alpha source project with these stated limits.
Keep public validation reports free of real usernames, session IDs, process
paths, and communication socket paths.
