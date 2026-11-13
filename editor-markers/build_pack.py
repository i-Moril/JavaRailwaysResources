#!/usr/bin/env python3
"""Build the editor marker client pack with stable ZIP contents and timestamps."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'resourcepack'
OUTPUT = ROOT / 'distributions/JavaRailways-editor-markers-26.1.2.zip'


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in SOURCE.rglob('*') if p.is_file()):
            entry = ZipInfo(path.relative_to(SOURCE).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    print(OUTPUT)


if __name__ == '__main__':
    main()
