"""Identify a local Codex TUI without guessing from most-recent project activity."""
from __future__ import annotations

import json
import ntpath
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import subprocess


def title_parts(title):
    # Codex's spinner is a Braille glyph, not part of the thread name.
    title = re.sub(r'^[\s\u2800-\u28ff]+', '', title)
    return [part.strip() for part in title.split(' | ') if part.strip()]


def directory_key(value):
    # WezTerm file URLs can expose Windows paths as /D:/project/.
    value = str(value)
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    if re.match(r'^/[A-Za-z]:[/\\]', value):
        value = value[1:]
    if re.match(r'^[A-Za-z]:[/\\]', value) or value.startswith('\\\\'):
        return ntpath.normcase(ntpath.normpath(value))
    return str(Path(value).resolve())


def state_candidates(home, title, cwd, directory_only=False):
    databases = sorted(home.glob('state_[0-9]*.sqlite'), key=lambda p: int(re.search(r'state_(\d+)', p.name)[1]), reverse=True)
    if not databases:
        return []
    parts = title_parts(title)
    if not parts and not directory_only:
        return []
    # A sqlite3 connection context manager ends transactions; it does not close
    # the connection. Close explicitly so no read handles survive detection.
    with closing(sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as conn:
        columns = {row[1] for row in conn.execute('pragma table_info(threads)')}
        required = {'id', 'rollout_path', 'cwd', 'title', 'archived'}
        if not required.issubset(columns):
            raise ValueError('The local Codex index schema is unsupported. Use open --rollout FILE instead.')
        name = 'name' if 'name' in columns else 'title'
        sql = f'select id,rollout_path,cwd,{name},title from threads where archived=0'
        rows = conn.execute(sql).fetchall()
    matches = []
    for sid, path, directory, label, original_title in rows:
        if not directory_only and (label or original_title) not in parts:
            continue
        if directory_only and (not cwd or directory_key(directory) != directory_key(cwd)):
            continue
        if not Path(path).is_file():
            continue
        matches.append({'id': sid, 'rollout': path, 'cwd': directory, 'label': label or original_title,
                        'reason': 'choose current session' if directory_only else 'exact terminal title',
                        'needs_choice': directory_only})
    same_directory = [m for m in matches if cwd and directory_key(m['cwd']) == directory_key(cwd)]
    return same_directory or matches


def opened_rollouts(pid):
    try:
        result = subprocess.run(['lsof', '-a', '-p', str(pid), '-Fn'], capture_output=True, text=True, timeout=3)
    except FileNotFoundError:
        return []
    matches = {}
    for line in result.stdout.splitlines():
        if not line.startswith('n'):
            continue
        path = Path(line[1:])
        if not path.name.startswith('rollout-') or path.suffix != '.jsonl' or not path.is_file():
            continue
        try:
            with path.open(encoding='utf-8') as f:
                first = json.loads(f.readline())
            if first.get('type') != 'session_meta':
                continue
            meta = first['payload']
            sid = meta['id']
            existing = matches.get(sid)
            if existing is None or path.stat().st_mtime > Path(existing['rollout']).stat().st_mtime:
                matches[sid] = {'id': sid, 'rollout': str(path), 'cwd': meta.get('cwd', ''),
                                'label': meta.get('cwd', sid), 'reason': 'Codex process open session file'}
        except (OSError, ValueError, KeyError):
            continue
    return list(matches.values())


def windows_processes():
    # Read process identity/ancestry only, never command lines or environment.
    script = ('[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); '
              'Get-CimInstance Win32_Process | '
              'Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                             '-Command', script], capture_output=True, text=True, encoding='utf-8', timeout=10,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Cannot inspect local Windows processes. Use open --rollout FILE instead.')
    rows = json.loads(result.stdout)
    if isinstance(rows, dict):
        rows = [rows]
    return {int(row['ProcessId']): (int(row['ParentProcessId']), row['Name'].lower()) for row in rows}


def resolve_windows_codex_pid(pid):
    processes = windows_processes()
    current, visited = pid, set()
    # WezTerm on Windows can report a recently spawned tool below Codex.
    while current in processes and current not in visited:
        visited.add(current)
        parent, name = processes[current]
        if name == 'codex.exe':
            return current
        current = parent
    # It can also report the shell/node launcher above the native CLI.
    descendants = {pid}
    while True:
        expanded = descendants | {p for p, info in processes.items() if info[0] in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    candidates = [p for p in descendants if p in processes and processes[p][1] == 'codex.exe']
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError('当前窗格没有唯一的 Codex 进程。请先点击 Codex 所在窗格，再按快捷键。')


def resolve_posix_codex_pid(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True, timeout=2)
    if result.returncode == 0 and Path(result.stdout.strip()).name.lower() == 'codex':
        return pid
    # On macOS WezTerm can report PowerShell's foreground process group leader,
    # even while the child Codex TUI owns the terminal input. Walk that tree.
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,tty=,comm='], capture_output=True, text=True, timeout=2)
    processes = {}
    for line in result.stdout.splitlines():
        cells = line.split(None, 3)
        if len(cells) == 4 and cells[0].isdigit() and cells[1].isdigit():
            processes[int(cells[0])] = (int(cells[1]), cells[2], cells[3])
    source_tty = processes.get(pid, (0, '??', ''))[1]
    descendants = {pid}
    while True:
        expanded = descendants | {p for p, info in processes.items() if info[0] in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    candidates = [p for p in descendants if p in processes and source_tty != '??'
                  and processes[p][1] == source_tty and Path(processes[p][2]).name.lower() == 'codex']
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError('当前窗格没有唯一的 Codex 进程。请先点击 Codex 所在窗格，再按快捷键。')


def resolve_codex_pid(pid):
    if pid <= 0:
        raise ValueError('Invalid source process ID')
    return resolve_windows_codex_pid(pid) if os.name == 'nt' else resolve_posix_codex_pid(pid)


def detect(pid, title, cwd, home=None):
    home = home or Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    pid = resolve_codex_pid(pid)
    opened = [] if os.name == 'nt' else opened_rollouts(pid)
    if len(opened) == 1:
        return opened
    named = state_candidates(home, title, cwd)
    if named:
        if opened:
            ids = {m['id'] for m in opened}
            named = [m for m in named if m['id'] in ids]
        if named:
            return named
    if opened:
        return opened
    choices = state_candidates(home, title, cwd, directory_only=True)
    if choices:
        # Even a single old session in the project is not proof of the active ID.
        return choices
    # A resume argument alone can be stale after /fork; never use it as proof.
    raise ValueError('未找到当前会话的本地记录。请等待会话初始化完成后再次按快捷键。')
