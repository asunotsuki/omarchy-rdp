#!/usr/bin/env python3
"""Create an allowlisted source release ZIP and checksum, without user data."""
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode = True
from install import FILES

RELEASE_FILES = FILES + ('connections.example.json', 'test_rdp.py', 'test_install.py',
                         'package.py', 'PUBLISHING.md')


def build(source):
    version = json.loads((source / 'manifest.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Invalid release version')
    for name in RELEASE_FILES:
        if (source / name).is_symlink() or not (source / name).is_file():
            raise ValueError('Missing or symlinked release file: ' + name)
    directory = source / 'dist'
    directory.mkdir(exist_ok=True)
    stem = 'omarchy-rdp-' + version
    archive = directory / (stem + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
        for name in RELEASE_FILES:
            out.write(source / name, stem + '/' + name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n')
    return archive


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parent))
