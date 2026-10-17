"""Render the gallery in WezTerm and handle interactive navigation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

from .sessions import SessionImages, resolve_rollout
from .terminal import TerminalInput

def wezterm_binary():
    found = shutil.which("wezterm")
    if found:
        return found
    mac = Path("/Applications/WezTerm.app/Contents/MacOS/wezterm")
    if mac.is_file():
        return str(mac)
    raise ValueError("WezTerm was not found. Install WezTerm or add it to PATH.")

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
