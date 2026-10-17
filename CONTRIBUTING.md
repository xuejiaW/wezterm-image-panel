# Contributing

Use Python 3.9+ and a separate virtual environment. The runtime has no third-party
Python dependencies. Run the headless suite before submitting a change:

```sh
python -m unittest discover -v
python scripts/check_release.py
```

With WezTerm installed, `wezterm --config-file scripts/check_wezterm.lua show-keys
--lua` exercises the Lua integration using mock panes without opening a GUI.

Tests must use temporary synthetic logs and mocked external processes. Do not
read a contributor's Codex home, modify their WezTerm config, or depend on real
session images. Put local experiments and draft captures in `.codex-local/`.

For GUI changes, run the macOS checklist in [VALIDATION.md](VALIDATION.md) and
state precisely what was checked. Headless tests do not prove terminal image
rendering, focus handling, or shortcut behavior. Linux/WSL support requires
its own validation; do not infer it from a passing Windows parser test.

Use clear English names and comments in source. Keep the Chinese user guide in
sync when changing installation or user-facing behavior. Include a concise
behavior description and relevant validation in pull requests.
