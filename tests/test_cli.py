from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wezterm_image_panel.cli import main
from wezterm_image_panel.sessions import SessionImages
from wezterm_image_panel.viewer import image_dimensions, render
from examples.create_demo_session import create, png
from scripts.check_release import findings


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(arguments)
        return status, out.getvalue(), err.getvalue()

    def test_synthetic_demo_uses_three_distinct_readable_images(self):
        path = create(self.root / 'rollout-demo-session.jsonl')
        status, out, err = self.run_cli([
            'inspect', '--rollout', str(path), '--cache-dir', str(self.root / 'cache')])
        self.assertEqual((status, err), (0, ''))
        report = json.loads(out)
        self.assertEqual((report['images'], report['errors']), (3, 0))
        self.assertEqual(len({item['sha256'] for item in report['items']}), 3)
        for item in report['items']:
            self.assertEqual(image_dimensions(Path(item['path'])), (640, 360))

    def test_demo_refuses_to_overwrite_existing_session(self):
        path = self.root / 'existing.jsonl'
        path.write_text('keep this file', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            create(path)
        self.assertEqual(path.read_text(encoding='utf-8'), 'keep this file')

    def test_multiple_panels_can_cache_the_same_new_image(self):
        data = png(0)
        cache = self.root / 'shared-cache'

        def snapshot(_):
            reader = SessionImages(self.root / 'unused.jsonl', cache)
            reader.add_bytes(data, 'synthetic image')
            return reader.images[0].path

        with ThreadPoolExecutor(max_workers=8) as pool:
            paths = list(pool.map(snapshot, range(16)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(paths[0].read_bytes(), data)
        self.assertEqual(list(cache.glob('.image-*')), [])

    def test_truncated_image_header_leaves_a_browsable_error(self):
        reader = SessionImages(self.root / 'unused.jsonl', self.root / 'cache')
        reader.add_bytes(b'\x89PNG\r\n\x1a\n', 'truncated synthetic image')
        output = io.StringIO()
        with redirect_stdout(output), patch('wezterm_image_panel.viewer.subprocess.run') as process:
            status = render(reader, 0, False, 'unused-wezterm', (80, 24))
        self.assertFalse(status['render_ok'])
        self.assertIn('Cannot read image dimensions', status['render_error'])
        self.assertIn('browse', output.getvalue())
        process.assert_not_called()

    def test_sessions_skips_incomplete_and_unrelated_logs(self):
        create(self.root / 'rollout-demo-session.jsonl')
        (self.root / 'rollout-incomplete.jsonl').write_text('{', encoding='utf-8')
        (self.root / 'rollout-unrelated.jsonl').write_text('[]\n', encoding='utf-8')
        status, out, err = self.run_cli(['sessions', '--sessions-dir', str(self.root)])
        self.assertEqual((status, err), (0, ''))
        self.assertEqual(out.strip(), 'demo-session  .')

    def test_invalid_intervals_fail_before_starting_wezterm(self):
        for value in ['0', '-1', 'nan', 'inf']:
            with self.subTest(interval=value):
                status, out, err = self.run_cli(['open', '--interval', value])
                self.assertEqual(status, 1)
                self.assertIn('Polling interval', err)

    def test_negative_session_limit_is_rejected(self):
        status, out, err = self.run_cli(['sessions', '--limit', '-1'])
        self.assertEqual(status, 1)
        self.assertIn('--limit', err)

    def test_redirected_viewer_requires_a_terminal(self):
        status, out, err = self.run_cli(['view'])
        self.assertEqual(status, 1)
        self.assertIn('needs a terminal', err)

    def test_release_guard_rejects_private_artifacts_and_identifiers(self):
        self.assertTrue(findings('.codex-local/capture.txt', b'private'))
        self.assertTrue(findings('session.jsonl', b'{}'))
        secret = ('ghp_' + 'A' * 36).encode()
        self.assertIn('credential format', findings('settings.txt', secret))
        machine_path = ('/Users/' + 'private-person/example').encode()
        self.assertIn('machine home path', findings('report.txt', machine_path))
        session_id = '-'.join(['a' * 8, 'b' * 4, 'c' * 4, 'd' * 4, 'e' * 12])
        self.assertIn('real-looking session UUID', findings('report.txt', session_id.encode()))
        self.assertEqual(findings('README.md', b'Use YOUR_SESSION_ID and ~/tools'), [])


if __name__ == '__main__':
    unittest.main()
