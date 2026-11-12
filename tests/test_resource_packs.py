import json
import struct
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dimensions(path):
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    offset = 8
    payload = []
    header = None
    while offset < len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + size]
        assert zlib.crc32(kind + chunk) == struct.unpack_from('>I', data, offset + 8 + size)[0]
        if kind == b'IHDR': header = struct.unpack('>IIBBBBB', chunk)
        if kind == b'IDAT': payload.append(chunk)
        offset += 12 + size
    width, height, depth, color, compression, filter_method, interlace = header
    assert (depth, color, compression, filter_method, interlace) == (8, 2, 0, 0, 0)
    raw = zlib.decompress(b''.join(payload))
    stride = width * 3 + 1
    assert len(raw) == stride * height
    assert all(raw[y * stride] in range(5) for y in range(height))
    return width, height


class ResourcePackTest(unittest.TestCase):
    def test_editor_marker_font_and_masks(self):
        pack = ROOT / 'editor-markers/resourcepack'
        meta = read_json(pack / 'pack.mcmeta')['pack']
        self.assertEqual([84, 0], meta['min_format'])
        self.assertEqual(meta['min_format'], meta['max_format'])
        provider, = read_json(pack / 'assets/javarailways/font/editor_markers.json')['providers']
        self.assertEqual(('bitmap', 8, 7, ['\ue100\ue101\ue102']), (provider['type'], provider['height'], provider['ascent'], provider['chars']))
        namespace, name = provider['file'].split(':')
        png = (pack / 'assets' / namespace / 'textures' / name).read_bytes()
        self.assertEqual((48, 16), struct.unpack('>II', png[16:24]))
        offset = 8
        chunks = []
        while offset < len(png):
            size = struct.unpack_from('>I', png, offset)[0]
            kind = png[offset + 4:offset + 8]
            data = png[offset + 8:offset + 8 + size]
            self.assertEqual(zlib.crc32(kind + data), struct.unpack_from('>I', png, offset + 8 + size)[0])
            if kind == b'IHDR':
                self.assertEqual((8, 6, 0, 0, 0), tuple(data[8:13]))
            if kind == b'IDAT': chunks.append(data)
            offset += 12 + size
        raw = zlib.decompress(b''.join(chunks))
        rows = []
        for y in range(16):
            row = raw[y * 193:(y + 1) * 193]
            self.assertEqual(0, row[0])
            rows.append(row[1:])
        for glyph in range(3):
            pixels = [rows[y][(glyph * 16 + x) * 4:(glyph * 16 + x + 1) * 4] for y in range(16) for x in range(16)]
            self.assertTrue(any(p[3] for p in pixels))
            self.assertEqual(glyph != 2, any(p[3] == 0 for p in pixels))
            self.assertTrue(all(p[3] in (0, 255) and (p[3] == 0 or p[:3] == b'\xff\xff\xff') for p in pixels))
            self.assertTrue(any(rows[y][(glyph * 16 + 15) * 4 + 3] == 255 for y in range(16)))

    def test_four_light_and_route_indicator_assets(self):
        groups = [('signals/jr-four-light/resourcepack', 'four_light_signal', ['stop', 'caution', 'slow', 'proceed', 'housing']),
                  ('signals/route-indicator/resourcepack', 'route_indicator', ['closed'] + list(map(str, range(10))) + ['housing'])]
        for base, prefix, states in groups:
            pack = ROOT / base
            self.assertEqual([75, 0], read_json(pack / 'pack.mcmeta')['pack']['min_format'])
            models = {}
            for state in states:
                wrapper = read_json(pack / f'assets/jr/items/{prefix}_{state}.json')['model']
                self.assertEqual('minecraft:model', wrapper['type'])
                namespace, key = wrapper['model'].split(':')
                model = read_json(pack / f'assets/{namespace}/models/{key}.json')
                for element in model['elements']:
                    for face in element['faces'].values():
                        reference = face['texture']
                        self.assertTrue(reference.startswith('#') and reference[1:] in model['textures'])
                for texture in model['textures'].values():
                    namespace, key = texture.split(':')
                    width, height = dimensions(pack / f'assets/{namespace}/textures/{key}.png')
                    self.assertGreater(width * height, 0)
                for element in model['elements']:
                    for key in ('from', 'to'):
                        self.assertTrue(all(-16 <= v <= 32 for v in element[key]))
                models[state] = model['elements']
            if prefix == 'route_indicator':
                pixel = next(e for e in models['2'] if e['name'] == 'pixel_1_0')
                self.assertEqual(10.8, pixel['from'][0])
                self.assertEqual({'north'}, set(pixel['faces']))
                self.assertEqual([], models['closed'])
                self.assertEqual(10, len({json.dumps(models[str(n)], sort_keys=True) for n in range(10)}))
                self.assertTrue(all(models[str(n)] for n in range(10)))
            else:
                self.assertEqual(29, len(models['housing']))
                dark = {e['name']: e for e in models['housing'] if e['name'].endswith('pixel lens')}
                self.assertEqual(4, len(dark))
                lamps = {'stop': [2], 'caution': [3], 'slow': [1, 4], 'proceed': [4]}
                uv = {'stop': [4.0], 'caution': [8.0], 'slow': [8.0, 12.0], 'proceed': [12.0]}
                lower = {1: 14.0, 2: 5.0, 3: -3.0, 4: -12.0}
                for state, ids in lamps.items():
                    lit = models[state]
                    self.assertEqual([f'lamp {i} pixel lens' for i in ids], [e['name'] for e in lit])
                    for index, e in enumerate(lit):
                        self.assertEqual(lower[ids[index]], e['from'][1])
                        u = uv[state][index]
                        self.assertEqual([u, 0.0, u + 4.0, 8.0], e['faces']['north']['uv'])
                        self.assertEqual({'north'}, set(e['faces']))
                        for end in ('from', 'to'):
                            self.assertEqual(dark[e['name']][end][:2], e[end][:2])
                            self.assertAlmostEqual(.05, dark[e['name']][end][2] - e[end][2])

if __name__ == '__main__':
    unittest.main()
