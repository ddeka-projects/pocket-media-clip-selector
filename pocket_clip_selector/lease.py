"""One active page; authorization stays locked through each durable mutation."""

from contextlib import contextmanager
import re
import secrets
import threading
import time

from .errors import AppError


class ControllerLease:
    def __init__(self, clock=time.monotonic, ttl=15.0):
        self.clock = clock
        self.ttl = ttl
        self.lock = threading.RLock()
        self.page = None
        self.token = None
        self.expires = 0.0

    def _expire(self):
        if self.clock() >= self.expires:
            self.page = self.token = None

    def claim(self, page: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", page):
            raise AppError("Invalid page identity.")
        with self.lock:
            self._expire()
            if self.page and self.page != page:
                raise AppError("Clip Selector is open elsewhere", 423, "lease_conflict")
            # A new generation also prevents a delayed pagehide release from
            # revoking a page that has just returned from Safari's back cache.
            self.token = secrets.token_urlsafe(32)
            self.page = page
            self.expires = self.clock() + self.ttl
            return {"token": self.token, "ttl": self.ttl, "heartbeat_interval": 5}

    def _authorize(self, page, token):
        self._expire()
        if not self.page:
            raise AppError("Reconnect before using Clip Selector.", 409, "lease_expired")
        if page != self.page or not token or not secrets.compare_digest(token, self.token):
            raise AppError("Clip Selector is open elsewhere", 423, "lease_conflict")

    @contextmanager
    def authorized(self, page, token):
        with self.lock:
            self._authorize(page, token)
            yield

    def heartbeat(self, page, token):
        with self.authorized(page, token):
            self.expires = self.clock() + self.ttl
            return {"ttl": self.ttl}

    def release(self, page, token):
        with self.lock:
            self._expire()
            if self.page:
                self._authorize(page, token)
                self.page = self.token = None
