import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from session_detection import (detect, state_candidates, opened_rollouts,
                               resolve_posix_codex_pid, resolve_windows_codex_pid)


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.db = self.home / 'state_5.sqlite'
        self.conn = sqlite3.connect(self.db)
        self.addCleanup(self.conn.close)
        self.conn.execute('create table threads (id text, rollout_path text,cwd text,name text,title text,archived integer)')

    def add(self, sid, name, cwd):
        path = self.home / f'rollout-{sid}.jsonl'
        path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': sid, 'cwd': cwd}})+'\n')
        self.conn.execute('insert into threads values (?,?,?,?,?,0)',(sid,str(path),cwd,name,'original user message'))
        self.conn.commit()
        return path

    def test_exact_renamed_title_and_spinner(self):
        self.add('one', '排查图片', '/a')
        self.add('two', '另一个会话', '/a')
        matches = state_candidates(self.home, '⠏ 排查图片 | a', '/a')
        self.assertEqual([m['id'] for m in matches], ['one'])

    def test_duplicate_name_prefers_directory_but_never_latest(self):
        self.add('one', 'same', '/a')
        self.add('two', 'same', '/b')
        self.assertEqual([m['id'] for m in state_candidates(self.home,'same | a','/a')],['one'])
        self.add('three','same','/a')
        self.assertEqual(len(state_candidates(self.home,'same | a','/a')),2)

    def test_plain_project_title_is_not_a_session_match(self):
        self.add('one','task','/a')
        self.assertEqual(state_candidates(self.home,'Codex | a','/a'),[])
        choices=state_candidates(self.home,'Codex | a','/a',directory_only=True)
        self.assertTrue(choices[0]['needs_choice'])

    def test_windows_wezterm_file_url_matches_native_directory(self):
        self.add('one', 'task', r'\\?\D:\demo project')
        self.add('two', 'task', r'E:\another project')
        matches = state_candidates(self.home, 'task', '/D:/demo project/')
        self.assertEqual([item['id'] for item in matches], ['one'])
        self.assertEqual(len(state_candidates(self.home, '', '/d:/demo project/', directory_only=True)), 1)

    def test_readonly_detection_connection_is_closed(self):
        self.add('one', 'task', '/a')
        connect = sqlite3.connect
        opened = []

        def track(*args, **kwargs):
            connection = connect(*args, **kwargs)
            opened.append(connection)
            return connection

        with patch('session_detection.sqlite3.connect', side_effect=track):
            self.assertEqual(len(state_candidates(self.home, 'task | a', '/a')), 1)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute('select 1')

    def test_changed_index_schema_has_explicit_rollout_fallback(self):
        self.conn.execute('drop table threads')
        self.conn.execute('create table threads (id text)')
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, '--rollout'):
            state_candidates(self.home, 'task', '/a')

    @patch('session_detection.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_lsof_allows_index_fallback(self, run):
        self.assertEqual(opened_rollouts(42), [])

    @patch('session_detection.subprocess.run')
    def test_rollout_identity_comes_from_metadata_not_filename_suffix(self, run):
        path=self.add('root-thread','task','/a')
        renamed=path.with_name('rollout-root-thread_generation-uuid.jsonl')
        path.rename(renamed)
        run.return_value=subprocess.CompletedProcess([],0,stdout='n'+str(renamed)+'\n')
        self.assertEqual(opened_rollouts(42)[0]['id'],'root-thread')

    @patch('session_detection.resolve_codex_pid', side_effect=ValueError('没有唯一的 Codex'))
    def test_shell_with_stale_codex_title_is_rejected(self, resolve):
        self.add('one','task','/a')
        with self.assertRaisesRegex(ValueError,'没有唯一的 Codex'):
            detect(42,'task | a','/a',self.home)

    @patch('session_detection.subprocess.run')
    def test_powershell_foreground_group_resolves_codex_child_only_on_same_tty(self, run):
        run.side_effect = [subprocess.CompletedProcess([],0,stdout='/usr/bin/pwsh\n'),
            subprocess.CompletedProcess([],0,stdout='42 1 ttys003 /usr/bin/pwsh\n43 42 ttys003 /opt/bin/codex\n44 43 ?? /opt/bin/codex\n45 1 ttys004 /opt/bin/codex\n')]
        self.assertEqual(resolve_posix_codex_pid(42),43)

    @patch('session_detection.opened_rollouts', return_value=[])
    @patch('session_detection.resolve_codex_pid', return_value=42)
    def test_local_tui_title_resolution(self, resolve, opened):
        self.add('one','task','/a')
        self.assertEqual(detect(42,'task | a','/a',self.home)[0]['id'],'one')

    @patch('session_detection.windows_processes')
    def test_windows_tool_child_and_node_launcher_resolve_same_codex(self, processes):
        processes.return_value = {10: (1, 'pwsh.exe'), 11: (10, 'node.exe'),
                                  12: (11, 'codex.exe'), 13: (12, 'powershell.exe'),
                                  21: (1, 'codex.exe')}
        for pid in (10, 11, 12, 13):
            self.assertEqual(resolve_windows_codex_pid(pid), 12)

    @patch('session_detection.windows_processes')
    def test_windows_multiple_codex_children_are_not_guessed(self, processes):
        processes.return_value = {10: (1, 'pwsh.exe'), 11: (10, 'codex.exe'),
                                  12: (10, 'codex.exe')}
        with self.assertRaisesRegex(ValueError, '没有唯一的 Codex'):
            resolve_windows_codex_pid(10)
        with self.assertRaises(ValueError):
            resolve_windows_codex_pid(99)


if __name__ == '__main__':
    unittest.main()
