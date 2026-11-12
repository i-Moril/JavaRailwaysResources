// Deterministic, dependency-free authoring for three 16x16 white alpha-mask glyphs.
// Run from any directory: node editor-markers/generate-texture.mjs
import { deflateSync } from 'node:zlib';
import { writeFileSync } from 'node:fs';

const size = 16;
const glyphs = [
  // Direction: arrow tip at the top (+Y in the TextDisplay plane).
  (x, y) => (y <= 7 && Math.abs(x - 7.5) <= y + 0.5) || (y >= 7 && x >= 6 && x <= 9),
  // Boundary: double transverse bars, with a short connecting centre mark.
  (x, y) => (y >= 3 && y <= 5) || (y >= 10 && y <= 12) || (x >= 7 && x <= 8 && y >= 5 && y <= 10),
  // Coverage: solid rectangle, scaled to a thin short chord by the section overlay.
  () => true,
];
const width = size * glyphs.length;
const scanlines = Buffer.alloc(size * (width * 4 + 1));
for (let y = 0; y < size; y++) {
  for (let x = 0; x < width; x++) {
    const offset = y * (width * 4 + 1) + 1 + x * 4;
    const opaque = glyphs[Math.floor(x / size)](x % size, y);
    scanlines[offset] = scanlines[offset + 1] = scanlines[offset + 2] = 255;
    scanlines[offset + 3] = opaque ? 255 : 0;
  }
}
function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, bytes) {
  const name = Buffer.from(type);
  const result = Buffer.alloc(bytes.length + 12);
  result.writeUInt32BE(bytes.length, 0);
  name.copy(result, 4);
  bytes.copy(result, 8);
  result.writeUInt32BE(crc32(Buffer.concat([name, bytes])), bytes.length + 8);
  return result;
}
const header = Buffer.alloc(13);
header.writeUInt32BE(width, 0);
header.writeUInt32BE(size, 4);
header[8] = 8; // 8 bits per channel
header[9] = 6; // RGBA
writeFileSync(new URL('./resourcepack/assets/javarailways/textures/font/editor_markers.png', import.meta.url),
  Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header), chunk('IDAT', deflateSync(scanlines)), chunk('IEND', Buffer.alloc(0))]));
