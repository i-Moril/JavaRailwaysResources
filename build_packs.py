#!/usr/bin/env python3
"""Rebuild every client resource pack, including packs inside delivery bundles."""

from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 's100-and-rail'), str(ROOT / 'editor-markers')]

import build_display_overlay as displays
import build_pack as markers
import build_s100_transparency_pack as s100
import generate_display_glyphs as glyphs


def update_bundle(path, prefix, entries):
    # Keep the server-side payload intact while replacing its client resources.
    with ZipFile(path) as archive:
        bundle = {name: archive.read(name) for name in archive.namelist()
                  if not name.startswith(prefix)}
    bundle.update(entries)
    displays.archive(path, bundle)


def main():
    glyphs.main()
    s100.deterministic_zip(s100.DEFAULT_SOURCE, ROOT / 's100-and-rail/distributions/resourcepack.zip')
    s100.build(s100.DEFAULT_SOURCE, s100.DEFAULT_CONTROL, s100.DEFAULT_OPTIMIZED)
    displays.main()
    markers.main()

    for source, output in (
        ('rail/resourcepack', 'rail/distributions/resourcepack.zip'),
        ('signals/jr-four-light/resourcepack', 'signals/jr-four-light/distributions/jr-four-light-26.1.2.zip'),
        ('signals/route-indicator/resourcepack', 'signals/route-indicator/distributions/jr-route-indicator-resourcepack.zip'),
    ):
        s100.deterministic_zip(ROOT / source, ROOT / output)

    nested = 'rails/resourcepack.zip'
    update_bundle(ROOT / 'rail/distributions/rails.zip', nested,
                  {nested: (ROOT / 'rail/distributions/resourcepack.zip').read_bytes()})
    update_bundle(ROOT / 'signals/route-indicator/distributions/jr-route-indicator.zip',
                  'resourcepack/', displays.tree(ROOT / 'signals/route-indicator/resourcepack', 'resourcepack/'))
    print('Rebuilt all resource packs and bundled copies.')


if __name__ == '__main__':
    main()
