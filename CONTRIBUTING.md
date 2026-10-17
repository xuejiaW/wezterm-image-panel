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

## Commit messages

Follow the [Angular commit format](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md):
`type(scope): summary`, with an optional scope. Use `build`, `ci`, `docs`, `feat`,
`fix`, `perf`, `refactor`, or `test`. Start the summary in lowercase, use an
imperative verb, and omit its final period. This project limits headers to 100
characters. Explain the motivation in a body of at least 20 characters, separated
by a blank line; `docs` may omit the body. Put breaking changes in a
`BREAKING CHANGE:` footer. Prefer scopes such as `cli`, `packaging`, `terminal`,
`sessions`, and `wezterm` when they clarify the change.

```text
refactor(packaging): separate runtime code from development files

Keep the installed package independent of tests and release scripts so the
source checkout cannot hide missing package contents during validation.
```

Enable the local hook once per checkout:

```sh
git config --local core.hooksPath .githooks
```

The hook and CI use `scripts/check_commits.py` without Node.js dependencies.
CI checks commits introduced by the push or pull request. The original public
commit predates this enforcement; renaming it requires a coordinated history
rewrite rather than a normal follow-up commit.

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
