"""Small console adapter: POSIX cbreak input and native Windows console input."""
from __future__ import annotations

import os
import sys
import time


class WindowsKeys:
    """Translate getwch extended keys, including split prefix/key reads."""
    def __init__(self):
        self.extended = False

    def feed(self, characters):
        data = bytearray()
        for char in characters:
            if self.extended:
                data.extend({'K': b'\x1b[D', 'M': b'\x1b[C'}.get(char, b''))
                self.extended = False
            elif char in ('\x00', '\xe0'):
                self.extended = True
            else:
                data.extend(char.encode('utf-8'))
        return bytes(data)


class TerminalInput:
    def __enter__(self):
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            self.console = msvcrt
            self.keys = WindowsKeys()
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
            mode = wintypes.DWORD()
            if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(mode)):
                raise OSError('Cannot read Windows console mode; run in a local WezTerm pane.')
            self.old_mode = mode.value
            if not self.kernel.SetConsoleMode(self.handle, mode.value | 0x0004):
                raise OSError('Cannot enable virtual terminal output in this console.')
        else:
            import termios
            import tty
            self.old_mode = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin)
        return self

    def read(self, timeout):
        """Return bytes, None on timeout, or empty bytes on POSIX EOF."""
        if os.name == 'nt':
            deadline = time.monotonic() + timeout
            while True:
                characters = []
                while self.console.kbhit():
                    char = self.console.getwch()
                    characters.append(char)
                    if char in ('\x00', '\xe0'):
                        # The second half is already buffered by getwch, but
                        # kbhit need not report it as a new console event.
                        characters.append(self.console.getwch())
                if characters:
                    data = self.keys.feed(characters)
                    if data:
                        return data
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(.02, remaining))
        import select
        if select.select([sys.stdin], [], [], timeout)[0]:
            return os.read(sys.stdin.fileno(), 64)
        return None

    def __exit__(self, *exc):
        if os.name == 'nt':
            self.kernel.SetConsoleMode(self.handle, self.old_mode)
        else:
            import termios
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_mode)
