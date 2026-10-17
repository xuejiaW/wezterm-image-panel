import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from terminal_io import TerminalInput, WindowsKeys
from wezterm_image_panel import KeyDecoder


class WindowsKeyboardTests(unittest.TestCase):
    def test_extended_arrows_and_normal_keys_reach_same_actions(self):
        keys, decoder = WindowsKeys(), KeyDecoder()
        self.assertEqual(decoder.feed(keys.feed('\xe0K\x00M q')),
                         ['previous', 'next', 'follow', 'quit'])

    def test_split_extended_key_does_not_turn_right_into_a_letter(self):
        keys, decoder = WindowsKeys(), KeyDecoder()
        self.assertEqual(decoder.feed(keys.feed('\xe0')), [])
        self.assertEqual(decoder.feed(keys.feed('M')), ['next'])
        self.assertEqual(decoder.feed(keys.feed('\x00Hh')), ['previous'])

    def test_vt_arrow_input_and_repeated_keys_are_preserved(self):
        keys, decoder = WindowsKeys(), KeyDecoder()
        self.assertEqual(decoder.feed(keys.feed('\x1b[Djjl')),
                         ['previous', 'next', 'next', 'follow'])

    def test_buffered_arrow_suffix_is_read_without_waiting_for_another_key(self):
        terminal = TerminalInput()
        terminal.keys = WindowsKeys()
        terminal.console = Mock()
        terminal.console.kbhit.side_effect = [True, False]
        terminal.console.getwch.side_effect = ['\xe0', 'K']
        with patch('terminal_io.os', SimpleNamespace(name='nt')):
            self.assertEqual(KeyDecoder().feed(terminal.read(.01)), ['previous'])
