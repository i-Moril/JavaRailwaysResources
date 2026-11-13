#!/usr/bin/env python3
"""Rebuild every client resource pack, including packs inside delivery bundles."""

from pathlib import Path
import json
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


def build_combined_pack():
    entries = {}
    sources = (
        's100-and-rail/distributions/resourcepack-s100-transparency-1.21.11-26.2.zip',
        'signals/jr-four-light/distributions/jr-four-light-26.1.2.zip',
        'signals/route-indicator/distributions/jr-route-indicator-resourcepack.zip',
        'editor-markers/distributions/JavaRailways-editor-markers-26.1.2.zip',
    )
    for index, source in enumerate(sources):
        with ZipFile(ROOT / source) as archive:
            for name in archive.namelist():
                if name.endswith('/') or (name == 'pack.mcmeta' and index != 0):
                    continue
                data = archive.read(name)
                if name in entries and entries[name] != data:
                    raise ValueError(f'Conflicting resource in {source}: {name}')
                entries[name] = data
    # Keep S100's version-specific transparency overlay and every asset unchanged.
    metadata = json.loads(entries['pack.mcmeta'])
    metadata['pack']['description'] = 'JavaRailways test resources: S100, signals and editor markers'
    entries['pack.mcmeta'] = (json.dumps(metadata, indent=2) + '\n').encode()
    destination = ROOT / 'distributions/javarailways.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    displays.archive(destination, entries)
    return destination


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
    build_combined_pack()
    print('Rebuilt all resource packs and bundled copies.')


if __name__ == '__main__':
    main()
