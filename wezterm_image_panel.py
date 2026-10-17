#!/usr/bin/env python3
"""Read-only session watcher; image bytes go only to its own WezTerm pane."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from terminal_io import TerminalInput

MAX_IMAGE = 32 * 1024 * 1024
MAX_RECORD = 64 * 1024 * 1024
__version__ = "0.4.0"


def wezterm_binary():
    found = shutil.which("wezterm")
    if found:
        return found
    mac = Path("/Applications/WezTerm.app/Contents/MacOS/wezterm")
    if mac.is_file():
        return str(mac)
    raise ValueError("WezTerm was not found. Install WezTerm or add it to PATH.")


def cache_root():
    if sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        if not base.is_absolute():
            base = Path.home() / ".cache"
    return base / "wezterm-image-panel"


def clean(text):
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(text))


def image_dimensions(path):
    data = path.read_bytes()
    if data.startswith(b"\x89PNG"):
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 < len(data):
            if data[pos] != 255:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            length = int.from_bytes(data[pos:pos + 2], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[pos + 3:pos + 7])
                return w, h
            if length < 2:
                break
            pos += length
    if data[:4] == b"RIFF":
        kind = data[12:16]
        if kind == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if kind == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ValueError("Cannot read image dimensions")


def cell_aspect(binary):
    try:
        pane = int(os.environ["WEZTERM_PANE"])
        result = subprocess.run([binary, "cli", "list", "--format", "json"], capture_output=True, timeout=2)
        for item in json.loads(result.stdout):
            if item["pane_id"] == pane:
                size = item["size"]
                return (size["pixel_width"] / size["cols"]) / (size["pixel_height"] / size["rows"])
    except (ValueError, KeyError, ZeroDivisionError, subprocess.SubprocessError):
        pass
    return .5


@dataclass
class Image:
    path: Path
    digest: str
    source: str


class KeyDecoder:
    """Decode normal/application-mode arrows, fragmented input and key repeats."""
    def __init__(self):
        self.pending = b''

    def feed(self, data):
        self.pending += data
        actions = []
        while self.pending:
            if self.pending.startswith(b'\x1b'):
                if len(self.pending) == 1:
                    break
                if self.pending[1:2] == b'O':
                    if len(self.pending) < 3:
                        break
                    code = self.pending[2:3]
                    self.pending = self.pending[3:]
                    action = {b'D': 'previous', b'C': 'next'}.get(code)
                elif self.pending[1:2] == b'[':
                    match = re.match(rb'\x1b\[([0-9;:]*)([A-Za-z~])', self.pending)
                    if not match:
                        if len(self.pending) < 24:
                            break
                        self.pending = self.pending[1:]
                        continue
                    self.pending = self.pending[match.end():]
                    action = {b'D': 'previous', b'C': 'next'}.get(match[2])
                    if match[2] == b'u':
                        # Kitty/CSI-u functional key encodings.
                        action = {b'57350': 'previous', b'57351': 'next'}.get(match[1].split(b';')[0])
                else:
                    self.pending = self.pending[1:]
                    continue
            else:
                code = self.pending[:1].lower()
                self.pending = self.pending[1:]
                action = {b'h':'previous', b'k':'previous', b'j':'next', b'l':'follow',
                          b' ':'follow', b'o':'open', b'q':'quit', b'\x04':'quit'}.get(code)
            if action:
                actions.append(action)
        return actions


class SessionImages:
    def __init__(self, rollout: Path, cache: Path | None = None):
        self.rollout = rollout.expanduser().resolve()
        self.cache = (cache or cache_root()).expanduser().resolve()
        self.offset = 0
        self.identity = None
        self.pending = b""
        self.images: list[Image] = []
        self.seen = set()
        self.cwd = self.rollout.parent
        self.records = 0
        self.errors = 0
        self.calls = {}
        self.discarding = False

    def add_bytes(self, data: bytes, source: str, original: Path | None = None):
        if len(data) > MAX_IMAGE:
            raise ValueError("Image exceeds 32 MiB")
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = ".png"
        elif data.startswith(b"\xff\xd8\xff"):
            ext = ".jpg"
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            ext = ".gif"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"
        else:
            raise ValueError("Unsupported or invalid image signature")
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.seen:
            return
        # Snapshot local files too: later overwrites must not change old gallery entries.
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.cache / (digest + ext)
        if not path.exists():
            fd, temporary = tempfile.mkstemp(prefix=".image-", dir=self.cache)
            temporary = Path(temporary)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                try:
                    temporary.replace(path)
                except PermissionError:
                    # Another panel can publish/open the same completed snapshot.
                    if not path.is_file():
                        raise
            finally:
                temporary.unlink(missing_ok=True)
        self.seen.add(digest)
        self.images.append(Image(path, digest, source))

    def add_path(self, value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.cwd / path
        if path.is_file() and path.stat().st_size <= MAX_IMAGE:
            self.add_bytes(path.read_bytes(), str(path), path)

    def extract(self, value):
        if isinstance(value, list):
            for child in value:
                self.extract(child)
        elif isinstance(value, dict):
            kind = value.get("type")
            if kind in ("input_image", "output_image", "image"):
                url = value.get("image_url", value.get("url", ""))
                if isinstance(url, dict):
                    url = url.get("url", "")
                if isinstance(url, str) and url.startswith("data:image/"):
                    body = url.split(",", 1)[1]
                    if len(body) > MAX_IMAGE * 4 // 3 + 8:
                        raise ValueError("Encoded image exceeds limit")
                    self.add_bytes(base64.b64decode(body, validate=True), "inline session image")
                elif kind == "image" and isinstance(value.get("data"), str):
                    body = value["data"]
                    if len(body) > MAX_IMAGE * 4 // 3 + 8:
                        raise ValueError("Encoded image exceeds limit")
                    self.add_bytes(base64.b64decode(body, validate=True), "MCP image result")
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    self.extract(child)

    def consume(self, record):
        if not isinstance(record, dict):
            return
        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            return
        if record.get("type") == "session_meta":
            self.cwd = Path(payload.get("cwd") or self.cwd)
        # Ignore world_state snapshots: they replay earlier items and can be huge.
        if record.get("type") != "response_item":
            return
        kind = payload.get("type")
        if kind in ("function_call", "custom_tool_call"):
            name = payload.get("name", "")
            raw = payload.get("arguments", payload.get("input", {}))
            if name == "view_image" or name.endswith("__view_image"):
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                    path = args.get("path")
                    if isinstance(path, str):
                        self.calls[payload.get("call_id")] = path
                except (ValueError, AttributeError):
                    pass
        if kind in ("function_call_output", "custom_tool_call_output"):
            path = self.calls.pop(payload.get("call_id"), None)
            if path:
                try:
                    self.add_path(path)
                except (OSError, ValueError):
                    self.errors += 1
            output = payload.get("output")
            if isinstance(output, str) and output.lstrip().startswith(("{", "[")):
                try:
                    self.extract(json.loads(output))
                except ValueError:
                    pass
        self.extract(payload)

    def poll(self):
        try:
            stat = self.rollout.stat()
        except FileNotFoundError:
            return False
        identity = (stat.st_dev, stat.st_ino)
        if identity != self.identity or stat.st_size < self.offset:
            self.offset = 0
            self.pending = b""
            self.discarding = False
            self.calls.clear()
            self.identity = identity
        before = len(self.images)
        with self.rollout.open("rb") as f:
            f.seek(self.offset)
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                self.offset += len(chunk)
                parts = (self.pending + chunk).split(b"\n")
                self.pending = parts.pop()
                for line in parts:
                    if self.discarding:
                        self.discarding = False
                        continue
                    if len(line) > MAX_RECORD:
                        self.errors += 1
                        continue
                    try:
                        self.consume(json.loads(line))
                        self.records += 1
                    except (ValueError, OSError, KeyError, TypeError):
                        self.errors += 1
                if len(self.pending) > MAX_RECORD:
                    self.pending = b""
                    self.discarding = True
                    self.errors += 1
        return len(self.images) != before


def sessions_root(args):
    return args.sessions_dir or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"


def resolve_rollout(args):
    if args.rollout:
        path = args.rollout.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Session file does not exist: {path}")
        return path
    if not args.session:
        raise ValueError("Specify --session ID or --rollout FILE. Use 'sessions' to find an ID.")
    if not re.fullmatch(r"[a-zA-Z0-9-]{8,80}", args.session):
        raise ValueError("Invalid session ID")
    candidates = list(sessions_root(args).rglob(f"rollout-*{args.session}*.jsonl"))
    if len(candidates) != 1:
        raise ValueError(f"Session ID matched {len(candidates)} files; use a complete ID or --rollout.")
    return candidates[0]


def render(reader, index, follow, binary, size):
    cols, rows = size
    def line(row, text):
        sys.stdout.write(f"\x1b[{row};1H\x1b[2K" + clean(text)[:max(1, cols - 1)])
    sys.stdout.write("\x1b[2J\x1b[H")
    line(1, "WEZTERM IMAGE PANEL  |  REAL IMAGE PREVIEW")
    line(2, "Session: " + reader.rollout.stem[-36:])
    line(3, f"Image {index + 1 if reader.images else 0}/{len(reader.images)}  |  " + ("LIVE" if follow else "PAUSED"))
    error = ""
    if reader.images:
        item = reader.images[index]
        line(4, item.source)
        sys.stdout.write("\x1b[6;1H")
        sys.stdout.flush()
        try:
            w, h = image_dimensions(item.path)
        except (ValueError, IndexError, struct.error):
            error = "Cannot read image dimensions; browse to another image."
        else:
            # imgcat's width takes precedence over height. Fit to both bounds.
            width = max(1, min(cols - 2, int(max(1, rows - 9) * w / max(1, h) / cell_aspect(binary))))
            result = subprocess.run([binary, "imgcat", "--no-move-cursor", "--width", str(width), str(item.path)],
                                    stderr=subprocess.PIPE, timeout=15)
            if result.returncode:
                error = "Image display failed: " + result.stderr.decode(errors="replace")
    else:
        line(6, "Waiting for images in this session...")
    line(max(7, rows - 2), "Left/Right: browse  |  Space/L: follow latest  |  O: open  |  Q: close")
    line(max(8, rows - 1), error or f"Read-only watcher | skipped records: {reader.errors}")
    sys.stdout.flush()
    return {"render_ok": bool(reader.images) and not error,
            "render_error": clean(error),
            "rendered_sha256": reader.images[index].digest if reader.images and not error else None}


def view(args):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("The viewer needs a terminal. Use 'open' to launch a WezTerm pane.")
    binary = wezterm_binary()
    reader = SessionImages(resolve_rollout(args), args.cache_dir)
    index, follow = 0, True
    previous_size = None
    decoder = KeyDecoder()
    last_render = {}
    redraw = True
    try:
        with TerminalInput() as terminal:
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b]2;WezTerm Image Panel\x07")
            while True:
                changed = reader.poll()
                if follow and reader.images:
                    index = len(reader.images) - 1
                size = shutil.get_terminal_size((80, 24))
                if changed or redraw or size != previous_size:
                    last_render = render(reader, index, follow, binary, size)
                    previous_size = size
                    redraw = False
                if args.state_file:
                    state = {"session_file": str(reader.rollout), "images": len(reader.images),
                             "index": index, "follow": follow, "size": list(size), "errors": reader.errors,
                             "pane_id": os.environ.get("WEZTERM_PANE"), **last_render}
                    temp = args.state_file.with_suffix(".tmp")
                    temp.write_text(json.dumps(state), encoding="utf-8")
                    try:
                        temp.replace(args.state_file)
                    except PermissionError:
                        # Windows diagnostics readers can briefly deny delete sharing.
                        pass
                keys = terminal.read(args.interval)
                if keys is None:
                    continue
                if not keys:
                    break
                actions = decoder.feed(keys)
                if 'quit' in actions:
                    break
                for action in actions:
                    if action == 'previous' and reader.images:
                        index = max(0, index - 1)
                        follow = False
                    elif action == 'next' and reader.images:
                        index = min(len(reader.images) - 1, index + 1)
                        follow = False
                    elif action == 'follow':
                        follow = not follow
                        if follow and reader.images:
                            index = len(reader.images) - 1
                    elif action == 'open' and reader.images:
                        if os.name == 'nt':
                            os.startfile(reader.images[index].path)
                        else:
                            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(reader.images[index].path)],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                redraw = bool(actions)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


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
        if args.command in ("auto-view", "identify"):
            if args.command == 'auto-view' and args.source_pane:
                owner = base64.b64encode(args.source_pane.encode()).decode()
                print('\x1b]1337;SetUserVar=WEZTERM_IMAGE_PANEL_OWNER=' + owner + '\x07', end='', flush=True)
            from session_detection import detect
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
            child = [sys.executable, str(Path(__file__).resolve()), "view", "--rollout", str(path), "--interval", str(args.interval)]
            if args.cache_dir:
                child += ["--cache-dir", str(args.cache_dir)]
            if args.state_file:
                child += ["--state-file", str(args.state_file)]
            if args.standalone:
                profile = Path(__file__).with_name("preview.wezterm.lua")
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
                command = [binary, "cli", "split-pane", "--pane-id", str(pane), "--right", "--percent", str(args.percent), "--"] + child
            subprocess.run(command, check=True, timeout=10)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("wezterm-image-panel: " + str(exc), file=sys.stderr)
        if args.command == 'auto-view' and sys.stdin.isatty():
            input('\n按 Enter 关闭预览窗格。')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
