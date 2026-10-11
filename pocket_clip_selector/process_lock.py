"""OS-owned library lock, outside the media tree; released even after a crash."""

import hashlib
import os
from pathlib import Path
import tempfile


class ProcessLock:
    def __init__(self, library: Path):
        identity = os.path.normcase(str(library.resolve()))
        self.name = "PocketClipSelector-" + hashlib.sha256(identity.encode()).hexdigest()
        self.handle = None

    def acquire(self):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            # Local is sufficient for the supported current-user logon deployment.
            handle = self.kernel.CreateMutexW(None, False, "Local\\" + self.name)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                self.kernel.CloseHandle(handle)
                raise RuntimeError("Another Clip Selector server already uses this library. Stop it first.")
            self.handle = handle
        else:
            # Enables automated checks on the development host; Windows uses a mutex.
            import fcntl
            path = Path(tempfile.gettempdir()) / (self.name + ".lock")
            self.handle = path.open("a+b")
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                self.handle.close()
                self.handle = None
                raise RuntimeError("Another Clip Selector server already uses this library. Stop it first.") from error

    def close(self):
        if self.handle is not None:
            if os.name == "nt":
                self.kernel.CloseHandle(self.handle)
            else:
                self.handle.close()
            self.handle = None
