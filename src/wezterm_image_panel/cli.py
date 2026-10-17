"""Command entry points for local Codex image previews in WezTerm."""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from . import __version__
from .sessions import SessionImages, cache_root, resolve_rollout, sessions_root
from .viewer import clean, view, wezterm_binary

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("view", "open", "inspect"):
        p = sub.add_parser(name)
        p.add_argument("--session", help="Exact Codex session UUID (or unambiguous prefix)")
        p.add_argument("--rollout", type=Path, help="Explicit session JSONL path")
        p.add_argument("--sessions-dir", type=Path)
        p.add_argument("--cache-dir", type=Path)
        if name in ("view", "open"):
            p.add_argument("--interval", type=float, default=.5)
            p.add_argument("--state-file", type=Path, help=argparse.SUPPRESS)
        if name == "open":
            p.add_argument("--pane-id", type=int, help="Codex pane to split; defaults to WEZTERM_PANE")
            p.add_argument("--new-window", action="store_true")
            p.add_argument("--standalone", action="store_true", help="Independent WezTerm preview window with a minimal profile")
            p.add_argument("--percent", type=int, default=40)
        if name == "view":
            p.add_argument("--source-pane", default="", help=argparse.SUPPRESS)
    p = sub.add_parser("sessions", help="List recent session IDs and working directories")
    p.add_argument("--sessions-dir", type=Path)
    p.add_argument("--limit", type=int, default=15)
    sub.add_parser("doctor", help="Check runtime prerequisites")
    p = sub.add_parser("auto-view", help="Shortcut entry point: identify the source Codex pane automatically")
    p.add_argument("--source-pid", type=int, required=True)
    p.add_argument("--source-title", default="")
    p.add_argument("--source-cwd", default="")
    p.add_argument("--source-pane", default="")
    p.add_argument("--state-file", type=Path, help=argparse.SUPPRESS)
    p = sub.add_parser("identify", help="Inspect automatic session detection without opening a viewer")
    p.add_argument("--source-pid", type=int, required=True)
    p.add_argument("--source-title", default="")
    p.add_argument("--source-cwd", default="")
    args = parser.parse_args(argv)
    try:
        if args.command in ("view", "open"):
            if not math.isfinite(args.interval) or args.interval < .05:
                raise ValueError("Polling interval must be a finite number of at least 0.05 seconds")
        if args.command == "sessions" and args.limit < 1:
            raise ValueError("--limit must be at least 1")
        if args.command in ("auto-view", "view") and args.source_pane:
            owner = base64.b64encode(args.source_pane.encode()).decode()
            print('\x1b]1337;SetUserVar=WEZTERM_IMAGE_PANEL_OWNER=' + owner + '\x07', end='', flush=True)
        if args.command in ("auto-view", "identify"):
            from .detection import detect
            candidates = detect(args.source_pid, args.source_title, args.source_cwd)
            if args.command == "identify":
                print(json.dumps(candidates, ensure_ascii=False, indent=2))
                return 0
            if len(candidates) > 1 or any(c.get('needs_choice') for c in candidates):
                print('无法唯一确认当前会话，请选择要查看的一项：\n')
                for i, item in enumerate(candidates, 1):
                    print(f'{i}. {clean(item["label"])}  {clean(item["cwd"])}  ({item["id"][-8:]})')
                answer = input('\n输入序号，或 Q 取消：').strip()
                if answer.lower() == 'q':
                    return 0
                if not answer.isdigit() or not 1 <= int(answer) <= len(candidates):
                    raise ValueError('选择序号无效')
                selected = candidates[int(answer) - 1]
            else:
                selected = candidates[0]
            args.rollout = Path(selected['rollout'])
            args.cache_dir = None
            args.interval = .5
            view(args)
        elif args.command == "doctor":
            binary = wezterm_binary()
            r = subprocess.run([binary, "cli", "list", "--format", "json"], capture_output=True, timeout=5)
            print(json.dumps({"python": sys.version.split()[0], "wezterm": binary,
                              "wezterm_running": r.returncode == 0, "cache": str(cache_root()),
                              "interactive_viewer_supported": os.name in ("posix", "nt")}, indent=2))
            return 0 if r.returncode == 0 else 1
        if args.command == "sessions":
            files = sorted(sessions_root(args).rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            for path in files[:args.limit]:
                try:
                    with path.open(encoding="utf-8") as f:
                        first = json.loads(f.readline())
                except (OSError, ValueError):
                    continue
                if not isinstance(first, dict) or first.get("type") != "session_meta":
                    continue
                meta = first.get("payload", {})
                if not isinstance(meta, dict):
                    continue
                print(clean(meta.get("id", path.stem[-36:])), clean(meta.get("cwd", "")), sep="  ")
        elif args.command == "inspect":
            reader = SessionImages(resolve_rollout(args), args.cache_dir)
            reader.poll()
            print(json.dumps({"session_file": str(reader.rollout), "images": len(reader.images), "errors": reader.errors,
                              "items": [{"path": str(i.path), "source": i.source, "sha256": i.digest} for i in reader.images]}, indent=2))
        elif args.command == "view":
            view(args)
        elif args.command == "open":
            path = resolve_rollout(args)
            binary = wezterm_binary()
            child = [sys.executable, "-m", "wezterm_image_panel", "view", "--rollout", str(path), "--interval", str(args.interval)]
            if args.cache_dir:
                child += ["--cache-dir", str(args.cache_dir)]
            if args.state_file:
                child += ["--state-file", str(args.state_file)]
            if args.standalone:
                profile = Path(__file__).with_name("assets") / "preview.wezterm.lua"
                if not profile.is_file():
                    profile = cache_root() / "preview.wezterm.lua"
                    profile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    profile.write_text("return { initial_cols=108, initial_rows=32, font_size=13, "
                                       "color_scheme='Catppuccin Mocha', enable_tab_bar=false, check_for_updates=false }")
                subprocess.Popen([binary, "--config-file", str(profile), "start", "--always-new-process", "--"] + child,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                print("Opened standalone preview window")
                return 0
            if args.new_window:
                command = [binary, "cli", "spawn", "--new-window", "--"] + child
            else:
                pane = args.pane_id if args.pane_id is not None else os.environ.get("WEZTERM_PANE")
                if pane is None:
                    raise ValueError("Run inside WezTerm, specify --pane-id, or use --new-window.")
                if not 10 <= args.percent <= 80:
                    raise ValueError("--percent must be between 10 and 80")
                child += ["--source-pane", str(pane)]
                command = [binary, "cli", "split-pane", "--pane-id", str(pane), "--right", "--percent", str(args.percent), "--"] + child
            subprocess.run(command, check=True, timeout=10)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("wezterm-image-panel: " + str(exc), file=sys.stderr)
        if args.command == 'auto-view' and sys.stdin.isatty():
            input('\n按 Enter 关闭预览窗格。')
        return 1
