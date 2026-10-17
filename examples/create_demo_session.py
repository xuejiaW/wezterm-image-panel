"""Create a synthetic, offline gallery without reading any Codex user data."""
import argparse
import base64
import json
from pathlib import Path
import struct
import time
import zlib


def png(index, width=640, height=360):
    """Generate an original RGB test card using only the standard library."""
    palettes = [(42, 106, 224), (15, 150, 120), (180, 90, 200)]
    accent = palettes[index % len(palettes)]
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            if 32 < x < width - 32 and 32 < y < height - 32:
                color = accent if x < 120 + index * 120 else (35, 43, 60)
                if height // 2 - 8 < y < height // 2 + 8:
                    color = (230, 235, 245)
            else:
                color = (20, 24, 35)
            raw.extend(color)

    def chunk(kind, body):
        checksum = zlib.crc32(kind + body) & 0xffffffff
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', checksum)

    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(raw))) + chunk(b'IEND', b''))


def create(destination, delay=0):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an existing log, including a real session by mistake.
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps({'type': 'session_meta', 'payload': {
            'id': 'demo-session', 'cwd': '.',
        }}) + '\n')
        stream.flush()
        for index in range(3):
            if delay:
                time.sleep(delay)
            encoded = base64.b64encode(png(index)).decode('ascii')
            stream.write(json.dumps({'type': 'response_item', 'payload': {
                'type': 'function_call_output', 'output': [{'type': 'input_image',
                'image_url': 'data:image/png;base64,' + encoded}],
            }}) + '\n')
            stream.flush()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=Path('.codex-local/demo/rollout-demo-session.jsonl'))
    parser.add_argument('--delay', type=float, default=0,
                        help='Seconds between image arrivals for a live demonstration')
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error('--delay must be between 0 and 60 seconds')
    print(create(args.output, args.delay))


if __name__ == '__main__':
    main()
