"""Manual page ownership; transfers wait for authorized mutations to finish."""

from contextlib import contextmanager
import re
import secrets
import threading

from .errors import AppError


class ControllerOwnership:
    def __init__(self):
        self.lock = threading.RLock()
        self.page = None
        self.token = None

    def claim(self, page: str, *, takeover=False):
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", page):
            raise AppError("Invalid page identity.")
        with self.lock:
            if self.page and self.page != page and not takeover:
                raise AppError("Clip Selector is open elsewhere", 423, "controller_occupied")
            # A fresh token invalidates every earlier grant, including a delayed
            # request from this same page after it explicitly re-enters editing.
            self.token = secrets.token_urlsafe(32)
            self.page = page
            return {"token": self.token}

    def _authorize(self, page, token):
        if not self.page:
            raise AppError("Editor control is no longer held. Take Control to edit here again.", 409, "controller_required")
        if page != self.page or not token or not token.isascii() or not secrets.compare_digest(token, self.token):
            raise AppError("Editor control was transferred to another page", 423, "controller_transferred")

    @contextmanager
    def authorized(self, page, token):
        with self.lock:
            self._authorize(page, token)
            yield

    def release(self, page, token):
        with self.lock:
            if self.page:
                self._authorize(page, token)
                self.page = self.token = None
