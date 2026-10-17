"""Inspect built archives without installing or extracting private content."""
from pathlib import Path
import tarfile
import zipfile

from check_release import findings


ROOT = Path(__file__).resolve().parents[1]


def members(path):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith('/'):
                    yield name, archive.read(name)
    else:
        with tarfile.open(path, 'r:gz') as archive:
            for item in archive.getmembers():
                if item.isfile():
                    with archive.extractfile(item) as stream:
                        yield item.name, stream.read()


def main():
    archives = sorted((ROOT / 'dist').glob('*.whl')) + sorted((ROOT / 'dist').glob('*.tar.gz'))
    if not any(p.suffix == '.whl' for p in archives) or not any(p.name.endswith('.tar.gz') for p in archives):
        print('Build both a wheel and source distribution first: python -m build')
        return 1
    failures = []
    for path in archives:
        count = 0
        for name, data in members(path):
            count += 1
            failures.extend((path.name, name, reason) for reason in findings(name, data))
        print(path.name + ': checked ' + str(count) + ' archive members')
    for archive, name, reason in failures:
        print(archive + ': ' + name + ': ' + reason)
    if failures:
        return 1
    print('Distribution privacy checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
