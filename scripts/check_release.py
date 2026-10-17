"""Check Git-visible source for private artifacts, selected secrets, and bad links.

This is a release guardrail, not a comprehensive secret or image-content scan.
Only paths and finding categories are printed; matched values are never echoed.
"""
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'.codex-local', 'evidence', '__pycache__', '.venv', 'venv'}
PRIVATE_SUFFIXES = {'.jsonl', '.sqlite', '.db', '.log', '.pem', '.p12', '.pfx',
                    '.keystore', '.zip', '.7z', '.pyc'}
PATTERNS = {
    'credential format': re.compile(
        r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|'
        r'AKIA[0-9A-Z]{16}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|'
        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'),
    'machine home path': re.compile(
        r'(?:/(?:Users)/[^/\s<>\"\']+|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<>\"\']+)'),
    'real-looking session UUID': re.compile(
        r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b'),
}


def findings(name, data):
    path = PurePosixPath(name)
    results = []
    if (set(path.parts) & PRIVATE_PARTS or path.suffix.lower() in PRIVATE_SUFFIXES
            or '.sqlite-' in path.name or path.name == '.env'
            or (path.name.startswith('.env.') and path.name != '.env.example')):
        results.append('private or generated artifact')
    if b'\x00' in data[:4096]:
        results.append('binary file needs a separate public-content review')
        return results
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        results.append('non-UTF-8 content needs review')
        return results
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            results.append(label)
    return results


def public_files():
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        check=True, capture_output=True,
    )
    return sorted({item.decode('utf-8') for item in result.stdout.split(b'\0') if item})


def main():
    try:
        names = public_files()
    except (OSError, subprocess.CalledProcessError):
        print('Run this check inside a Git checkout (git init is sufficient).')
        return 1
    failures = []
    for name in names:
        path = ROOT / name
        if not path.is_file():
            failures.append((name, 'tracked file is missing'))
            continue
        data = path.read_bytes()
        failures.extend((name, reason) for reason in findings(name, data))
        if path.suffix == '.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', data.decode('utf-8-sig')):
                target = target.split('#', 1)[0]
                if not target or urlparse(target).scheme:
                    continue
                linked = path.parent / unquote(target)
                if not linked.exists():
                    failures.append((name, 'broken relative documentation link: ' + target))
    for name, reason in failures:
        print(name + ': ' + reason)
    if failures:
        print('Release check failed: review the listed files before sharing.')
        return 1
    print('Release check passed for ' + str(len(names)) + ' Git-visible files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
