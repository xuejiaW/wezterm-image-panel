import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from wezterm_image_panel.detection import (detect, state_candidates, opened_rollouts,
                               resolve_posix_codex_pid, resolve_windows_codex_pid,
                               is_interactive_codex)


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

        with patch('wezterm_image_panel.detection.sqlite3.connect', side_effect=track):
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

    @patch('wezterm_image_panel.detection.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_lsof_allows_index_fallback(self, run):
        self.assertEqual(opened_rollouts(42), [])

    @patch('wezterm_image_panel.detection.subprocess.run')
    def test_rollout_identity_comes_from_metadata_not_filename_suffix(self, run):
        path=self.add('root-thread','task','/a')
        renamed=path.with_name('rollout-root-thread_generation-uuid.jsonl')
        path.rename(renamed)
        run.return_value=subprocess.CompletedProcess([],0,stdout='n'+str(renamed)+'\n')
        self.assertEqual(opened_rollouts(42)[0]['id'],'root-thread')

    @patch('wezterm_image_panel.detection.resolve_codex_pid', side_effect=ValueError('没有唯一的 Codex'))
    def test_shell_with_stale_codex_title_is_rejected(self, resolve):
        self.add('one','task','/a')
        with self.assertRaisesRegex(ValueError,'没有唯一的 Codex'):
            detect(42,'task | a','/a',self.home)

    @patch('wezterm_image_panel.detection.subprocess.run')
    def test_powershell_foreground_group_resolves_codex_child_only_on_same_tty(self, run):
        run.side_effect = [subprocess.CompletedProcess([],0,stdout='42 1 ttys003 /usr/bin/pwsh\n43 42 ttys003 /opt/bin/codex\n44 43 ?? /opt/bin/codex\n45 1 ttys004 /opt/bin/codex\n'),
                           subprocess.CompletedProcess([],0,stdout='43 /opt/bin/codex\n')]
        self.assertEqual(resolve_posix_codex_pid(42),43)

    @patch('wezterm_image_panel.detection.opened_rollouts', return_value=[])
    @patch('wezterm_image_panel.detection.resolve_codex_pid', return_value=42)
    def test_local_tui_title_resolution(self, resolve, opened):
        self.add('one','task','/a')
        self.assertEqual(detect(42,'task | a','/a',self.home)[0]['id'],'one')

    @patch('wezterm_image_panel.detection.windows_processes')
    def test_windows_tool_child_and_node_launcher_resolve_same_codex(self, processes):
        processes.return_value = {10: (1, 'pwsh.exe'), 11: (10, 'node.exe'),
                                  12: (11, 'codex.exe'), 13: (12, 'powershell.exe'),
                                  21: (1, 'codex.exe')}
        for pid in (10, 11, 12, 13):
            self.assertEqual(resolve_windows_codex_pid(pid), 12)

    @patch('wezterm_image_panel.detection.windows_processes')
    def test_windows_multiple_codex_children_are_not_guessed(self, processes):
        processes.return_value = {10: (1, 'pwsh.exe'), 11: (10, 'codex.exe'),
                                  12: (10, 'codex.exe')}
        with self.assertRaisesRegex(ValueError, '没有唯一的 Codex'):
            resolve_windows_codex_pid(10)
        with self.assertRaises(ValueError):
            resolve_windows_codex_pid(99)


class PosixProcessTests(unittest.TestCase):
    def process_query(self, rows, commands):
        """Supply synthetic ps output for both the old and new query shapes."""
        def query(args, **kwargs):
            if args[-1] == 'comm=':
                pid = int(args[args.index('-p') + 1])
                output = rows[pid][2] + '\n'
            elif args[-1] == 'pid=,args=':
                output = ''.join(f'{pid} {command}\n' for pid, command in commands.items())
            else:
                output = ''.join(f'{pid} {parent} {tty} {executable}\n'
                                 for pid, (parent, tty, executable) in rows.items())
            return subprocess.CompletedProcess(args, 0, stdout=output)
        return patch('wezterm_image_panel.detection.subprocess.run', side_effect=query)

    def test_same_terminal_app_server_is_not_a_second_codex_session(self):
        rows = {42: (1, 'ttys003', '/bin/zsh'),
                43: (42, 'ttys003', '/opt/bin/codex'),
                44: (43, 'ttys003', '/opt/bin/codex')}
        with self.process_query(rows, {43: '/opt/bin/codex resume example',
                                       44: '/opt/bin/codex app-server --listen stdio://'}):
            self.assertEqual(resolve_posix_codex_pid(42), 43)

    def test_reported_helper_pid_resolves_to_its_interactive_ancestor(self):
        rows = {42: (1, 'ttys003', '/bin/zsh'),
                43: (42, 'ttys003', '/opt/bin/codex'),
                44: (43, 'ttys003', '/opt/bin/codex')}
        with self.process_query(rows, {43: '/opt/bin/codex', 44: '/opt/bin/codex app-server'}):
            self.assertEqual(resolve_posix_codex_pid(44), 43)

    def test_helper_without_a_tui_is_not_accepted_as_a_session(self):
        rows = {42: (1, 'ttys003', '/bin/zsh'), 44: (42, 'ttys003', '/opt/bin/codex')}
        with self.process_query(rows, {44: '/opt/bin/codex app-server'}):
            with self.assertRaisesRegex(ValueError, '未找到交互式 Codex'):
                resolve_posix_codex_pid(42)

    def test_two_real_interactive_sessions_still_require_explicit_selection(self):
        rows = {42: (1, 'ttys003', '/bin/zsh'),
                43: (42, 'ttys003', '/opt/bin/codex'),
                44: (43, 'ttys003', '/opt/bin/codex'),
                45: (42, 'ttys003', '/opt/bin/codex')}
        with self.process_query(rows, {43: '/opt/bin/codex resume first',
                                       44: '/opt/bin/codex app-server',
                                       45: '/opt/bin/codex fork second'}):
            with self.assertRaisesRegex(ValueError, '多个交互式 Codex'):
                resolve_posix_codex_pid(42)

    def test_helpers_with_global_options_are_filtered_without_matching_prompt_text(self):
        for command in ('codex app-server', 'codex --config model="demo" app-server',
                        'codex --profile demo exec --json -', 'codex mcp-server'):
            with self.subTest(command=command):
                self.assertFalse(is_interactive_codex(command, '/opt/bin/codex'))
        for command in ('codex resume example', 'codex --model app-server',
                        'codex check the app-server output', 'codex -- app-server',
                        'codex inspect the app-server\'s logs'):
            with self.subTest(command=command):
                self.assertTrue(is_interactive_codex(command, '/opt/bin/codex'))

    def test_executable_paths_with_spaces_and_unknown_ttys(self):
        path = '/opt/demo tools/codex'
        self.assertFalse(is_interactive_codex(path + ' app-server', path))
        self.assertTrue(is_interactive_codex(path + ' resume example', path))
        for tty in ('?', '??', '-'):
            with self.subTest(tty=tty), self.process_query({42: (1, tty, path)}, {42: path}):
                with self.assertRaisesRegex(ValueError, '终端信息'):
                    resolve_posix_codex_pid(42)

    def test_missing_command_details_do_not_select_a_remaining_candidate(self):
        rows = {42: (1, 'ttys003', '/bin/zsh'),
                43: (42, 'ttys003', '/opt/bin/codex'),
                44: (43, 'ttys003', '/opt/bin/codex')}
        with self.process_query(rows, {43: '/opt/bin/codex'}):
            with self.assertRaisesRegex(ValueError, '运行模式'):
                resolve_posix_codex_pid(42)

    @unittest.skipUnless(os.name == 'posix', 'Requires native POSIX ps and a pseudo-terminal')
    def test_native_ps_distinguishes_same_tty_helper_processes(self):
        # The stand-in executables only wait on stdin/a FIFO. No real Codex,
        # authentication, user sessions, compiler, or GUI is involved.
        import pty
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # macOS system binaries carry protected flags that must not be
            # copied onto a temporary stand-in. Copy bytes and set our mode.
            shutil.copyfile(shutil.which('cat'), root / 'codex')
            (root / 'codex').chmod(0o700)
            os.mkfifo(root / 'app-server')
            script = (
                'import fcntl,json,subprocess,sys,termios,time; from pathlib import Path; '
                'fcntl.ioctl(0,termios.TIOCSCTTY,0); root=Path(sys.argv[1]); '
                'tui=subprocess.Popen([str(root/"codex")]); '
                'helper=subprocess.Popen([str(root/"codex"),"app-server"],cwd=root); '
                '(root/"ready.tmp").write_text(json.dumps({"tui":tui.pid,"helper":helper.pid})); '
                '(root/"ready.tmp").replace(root/"ready.json"); '
                'time.sleep(20)'
            )
            master, slave = pty.openpty()
            harness = subprocess.Popen([sys.executable, '-c', script, directory],
                                       stdin=slave, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not (root / 'ready.json').exists() and time.monotonic() < deadline:
                    if harness.poll() is not None:
                        self.fail(harness.stderr.read().decode(errors='replace'))
                    time.sleep(.02)
                self.assertTrue((root / 'ready.json').exists(), 'Process fixture failed to initialize')
                ready = json.loads((root / 'ready.json').read_text())
                self.assertEqual(resolve_posix_codex_pid(harness.pid), ready['tui'])
            finally:
                try:
                    os.killpg(harness.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                harness.wait(timeout=5)
                harness.stderr.close()
                os.close(slave)
                os.close(master)


if __name__ == '__main__':
    unittest.main()
