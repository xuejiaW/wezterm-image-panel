"""Validate this project's Angular-style commit messages using the standard library."""
import argparse
from pathlib import Path
import re
import subprocess


TYPES = ('build', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'test')
HEADER = re.compile(r'(' + '|'.join(TYPES) + r')(?:\([a-z][a-z0-9-]*\))?: (\S.*)')


def findings(message):
    lines = message.strip().splitlines()
    header = lines[0] if lines else ''
    reverted = header.startswith('revert: ')
    match = HEADER.fullmatch(header[8:] if reverted else header)
    if not match:
        return ['expected type(scope): summary; scope is optional']
    errors = []
    summary = match[2]
    if len(header) > 100:
        errors.append('header exceeds the project limit of 100 characters')
    if summary[0].isupper() or summary.endswith('.'):
        errors.append('start the summary in lowercase and omit its final period')
    if len(lines) > 1 and lines[1].strip():
        errors.append('separate the header and body with a blank line')
    body = '\n'.join(lines[2:]).strip()
    body = re.split(r'(?m)^(?:BREAKING CHANGE:|DEPRECATED:|(?:Fixes|Closes) #)', body)[0].strip()
    if (match[1] != 'docs' or body or reverted) and len(body) < 20:
        errors.append('include a body of at least 20 characters explaining why')
    if reverted and not re.search(r'(?m)^This reverts commit [0-9a-f]{40}\.?$', message):
        errors.append('include This reverts commit followed by the full original SHA')
    return errors


def git(*args):
    return subprocess.check_output(['git', *args]).decode('utf-8').strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--message-file', type=Path, help='Validate a commit-msg hook input')
    group.add_argument('--base', default='', help='Validate commits after this SHA')
    parser.add_argument('--head', default='HEAD')
    args = parser.parse_args(argv)
    try:
        if args.message_file:
            raw = args.message_file.read_bytes()
            message = subprocess.check_output(['git', 'stripspace', '--strip-comments'], input=raw).decode('utf-8')
            messages = [('commit message', message)]
        else:
            base = args.base if args.base and set(args.base) != {'0'} else ''
            commits = git('rev-list', '--reverse', f'{base}..{args.head}' if base else '-1', *([] if base else [args.head])).splitlines()
            messages = [(sha[:8], git('show', '-s', '--format=%B', sha)) for sha in commits]
        failed = False
        for label, message in messages:
            for error in findings(message):
                print(label + ': ' + error)
                failed = True
        if failed:
            return 1
        print('Angular commit checks passed for ' + str(len(messages)) + ' commit(s).')
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('Cannot validate commit messages: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
