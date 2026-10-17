# Contributing

Use Python 3.9+ and a separate virtual environment. The runtime has no third-party
Python dependencies. Install the package before running the headless suite:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/check_release.py
```

## Layout

- `src/wezterm_image_panel/cli.py`: command arguments and pane launching.
- `src/wezterm_image_panel/sessions.py`: selected Codex JSONL and image cache.
- `src/wezterm_image_panel/detection.py`: process and session identification.
- `src/wezterm_image_panel/viewer.py`: rendering and gallery navigation.
- `src/wezterm_image_panel/terminal.py`: Windows/POSIX console input.
- `tests/`: synthetic regression tests; `scripts/`: development checks.
- `integrations/`: WezTerm Lua integration; `examples/`: user examples.

Use `wezterm-image-panel` or `python -m wezterm_image_panel`. Do not add a second
launcher or expose internal module files as user entry points.

With WezTerm installed, `wezterm --config-file scripts/check_wezterm.lua show-keys
--lua` exercises the Lua integration using mock panes without opening a GUI.

Tests must use temporary synthetic logs and mocked external processes. Do not
read a contributor's Codex home, modify their WezTerm config, or depend on real
session images. Put local experiments and draft captures in `.codex-local/`.

For GUI changes, run the Windows/macOS checklist in [validation notes](docs/validation.md) and
state precisely what was checked. Headless tests do not prove terminal image
rendering, focus handling, or shortcut behavior. Linux/WSL support requires
its own validation; do not infer it from a passing Windows parser test.

Use clear English names and comments in source. Keep the Chinese user guide in
sync when changing installation or user-facing behavior. Include a concise
behavior description and relevant validation in pull requests.
