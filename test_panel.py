import base64
import json
from pathlib import Path
import tempfile
import unittest

from wezterm_image_panel import SessionImages, image_dimensions, KeyDecoder

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')


def output(data=PNG):
    return {'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': [
        {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(data).decode()}]}}


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'session.jsonl'
        self.file.touch()
        self.reader = SessionImages(self.file, self.root / 'cache')

    def append(self, record):
        with self.file.open('a') as f:
            f.write(json.dumps(record) + '\n')

    def test_incremental_partial_records_and_duplicate_image(self):
        raw = json.dumps(output()).encode() + b'\n'
        self.file.write_bytes(raw[:31])
        self.assertFalse(self.reader.poll())
        with self.file.open('ab') as f:
            f.write(raw[31:])
        self.assertTrue(self.reader.poll())
        self.assertEqual(self.reader.images[0].path.read_bytes(), PNG)
        self.append(output())
        self.assertFalse(self.reader.poll())
        self.assertEqual(len(self.reader.images), 1)

    def test_mcp_json_output_and_invalid_record_recovery(self):
        self.file.write_text('broken JSON\n')
        self.append({'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': json.dumps({
            'content': [{'type': 'image', 'data': base64.b64encode(PNG).decode(), 'mimeType': 'image/png'}]})}})
        self.assertTrue(self.reader.poll())
        self.assertEqual(self.reader.errors, 1)
        self.assertEqual(self.reader.images[0].source, 'MCP image result')

    def test_local_relative_image_snapshots_on_completion(self):
        image = self.root / 'a.png'
        image.write_bytes(PNG)
        self.append({'type': 'session_meta', 'payload': {'cwd': str(self.root)}})
        self.append({'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'view_image',
                     'call_id': 'a', 'arguments': json.dumps({'path': 'a.png'})}})
        self.reader.poll()
        self.assertEqual(len(self.reader.images), 0)
        self.append({'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'a', 'output': 'ok'}})
        self.assertTrue(self.reader.poll())
        image.write_bytes(b'overwritten')
        self.assertEqual(self.reader.images[0].path.read_bytes(), PNG)

    def test_rotation_and_truncation_keep_gallery_without_duplicates(self):
        self.append(output())
        self.reader.poll()
        self.file.unlink()
        self.append(output())
        self.assertFalse(self.reader.poll())
        self.file.write_text('{}\n')
        self.assertFalse(self.reader.poll())
        self.assertEqual(len(self.reader.images), 1)

    def test_no_images_from_world_state_or_other_sessions(self):
        self.append({'type': 'world_state', 'payload': output()})
        other = self.root / 'other.jsonl'
        other.write_text(json.dumps(output()) + '\n')
        self.assertFalse(self.reader.poll())
        self.assertEqual(len(self.reader.images), 0)

    def test_image_dimensions_used_for_aspect_ratio(self):
        self.append(output())
        self.reader.poll()
        self.assertEqual(image_dimensions(self.reader.images[0].path), (1, 1))

    def test_invalid_image_does_not_block_later_record(self):
        self.append(output(b'not an image'))
        self.append(output())
        self.assertTrue(self.reader.poll())
        self.assertEqual(self.reader.errors, 1)
        self.assertEqual(len(self.reader.images), 1)


class KeyboardTests(unittest.TestCase):
    def test_application_mode_and_repeated_arrows(self):
        self.assertEqual(KeyDecoder().feed(b'\x1bOD\x1b[C\x1b[D\x1b[D'),
                         ['previous','next','previous','previous'])

    def test_fragmented_arrow_sequence(self):
        decoder=KeyDecoder()
        self.assertEqual(decoder.feed(b'\x1b['),[])
        self.assertEqual(decoder.feed(b'D '),['previous','follow'])

    def test_modified_and_extended_arrows_and_exit(self):
        self.assertEqual(KeyDecoder().feed(b'\x1b[1;2D\x1b[57351uQ\n'),['previous','next','quit'])


if __name__ == '__main__':
    unittest.main()
