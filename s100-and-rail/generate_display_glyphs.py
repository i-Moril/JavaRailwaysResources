#!/usr/bin/env python3
"""Generate the deterministic bitmap glyphs used by train display XML (stdlib only)."""
import json
import math
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parent
PACK = ROOT / 'resourcepack'


def png(path, width, height, pixel):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\0' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    providers = []
    shapes = [(0xe004, 'ring', 18), (0xe005, 'dot', 18)]
    for codepoint, name, ink_width in shapes:
        # Preserve the existing circle textures. Their one-pixel ink-center
        # offset is explicitly compensated by the template (x - size / 9).
        def pixel(x, y, name=name, ink_width=ink_width):
            x -= 2
            filled = 0 <= x < ink_width
            if filled and name in ('ring', 'dot'):
                radius = math.hypot(x + .5 - 9, y + .5 - 9)
                filled = radius <= 9 and (name == 'dot' or radius >= 6)
            return (255, 255, 255, 255 if filled else 0)
        file = f'display/{name}.png'
        png(PACK / 'assets/javarailways/textures' / file, ink_width + 2, 18, pixel)
        providers.append({'type': 'bitmap', 'file': 'javarailways:' + file, 'height': 9, 'ascent': 7, 'chars': [chr(codepoint)]})
    font = PACK / 'assets/javarailways/font/display_geometry.json'
    font.parent.mkdir(parents=True, exist_ok=True)
    font.write_text(json.dumps({'providers': providers}, ensure_ascii=True, indent=2) + '\n')
    png(PACK / 'assets/minecraft/textures/item/art1st/tc/s100/display_background.png', 2, 2, lambda x, y: (0, 0, 0, 255))


if __name__ == '__main__':
    main()
