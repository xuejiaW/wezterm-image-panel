# Offline demonstration

Run these commands from the checkout with its Python environment activated.
The fixture generator uses only the standard library. Its images are generated
geometric test cards, not screenshots, real conversation output, or API results.

## Static gallery

```sh
python examples/create_demo_session.py
wezterm-image-panel inspect --rollout .codex-local/demo/rollout-demo-session.jsonl
wezterm-image-panel open --rollout .codex-local/demo/rollout-demo-session.jsonl --standalone
```

`inspect` should report three images and zero skipped records. Viewing requires
a supported terminal host. Use Left/Right to navigate, Space to resume following,
and Q to exit. The generator refuses to overwrite an existing destination.

## Images arriving over time

In terminal A:

```sh
python examples/create_demo_session.py --output .codex-local/demo/live-demo.jsonl --delay 5
```

While it is running, use terminal B:

```sh
wezterm-image-panel open --rollout .codex-local/demo/live-demo.jsonl --standalone
```

Three distinct images arrive five seconds apart. After the second appears,
pause on the first. The third should arrive without moving the paused gallery.
Press Space to return to the newest image.

## Recording public media

Use an isolated WezTerm window with only this fixture. Keep unrelated windows,
tabs, task names, shell history, usernames, and filesystem paths outside the
capture. Review every frame of a GIF before sharing it. Do not reuse real
session images just because the surrounding log is a synthetic fixture.

Save draft captures under `.codex-local/`, which is ignored and excluded from
distributions. Public media should be reviewed and added deliberately; no
recording is generated or published automatically.
