"""Read one selected Codex log and cache immutable image snapshots."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

MAX_IMAGE = 32 * 1024 * 1024
MAX_RECORD = 64 * 1024 * 1024

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

@dataclass
class Image:
    path: Path
    digest: str
    source: str

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
