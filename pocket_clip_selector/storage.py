"""Versioned project JSON, fresh reads, serialized edits, and atomic replacement."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading

from .errors import AppError
from .library import sort_key, validate_name
from .mp4 import duration


def valid_range(start, end):
    if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start):
        raise AppError("Start and end must be finite seconds, with 0 ≤ start < end.", 422, "invalid_range")


class SelectionStore:
    def __init__(self, library):
        self.library = library
        self.lock = threading.RLock()

    def media_duration(self, project, file):
        stream, info = self.library.open_media(project, file)
        with stream:
            return duration(stream, info.st_size)

    def _load(self, project):
        path = self.library.metadata(project)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            payload = b""
        revision = hashlib.sha256(payload).hexdigest()
        if not payload:
            if path.exists():
                raise AppError("Selections JSON is empty. Restore it from a backup before saving.", 500, "invalid_storage")
            return [], revision
        try:
            data = json.loads(payload)
            if type(data) is not dict or type(data.get("version")) is not int or data["version"] != 1:
                raise ValueError("unsupported format")
            records = data["selections"]
            if not isinstance(records, list):
                raise ValueError("expected selections list")
            ids = set()
            for record in records:
                if not isinstance(record, dict) or set(record) != {"id", "file", "start", "end"}:
                    raise ValueError("invalid selection")
                if not isinstance(record["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", record["id"]) or record["id"] in ids:
                    raise ValueError("invalid or duplicate id")
                ids.add(record["id"])
                validate_name(record["file"])
                if Path(record["file"]).suffix.lower() != ".mp4":
                    raise ValueError("expected MP4 identity")
                valid_range(record["start"], record["end"])
            return records, revision
        except (ValueError, KeyError, TypeError, AppError) as error:
            raise AppError("Selections JSON is damaged or uses an unsupported format. The file was left untouched; restore a valid backup.", 500, "invalid_storage") from error

    def _snapshot(self, project, records, revision):
        ordered = sorted(records, key=lambda row: (*sort_key(row["file"]), row["start"], row["end"], row["id"]))
        return {"revision": revision, "selections": [
            {**row, "available": self.library.available(project, row["file"])} for row in ordered
        ]}

    def list(self, project):
        with self.lock:
            return self._snapshot(project, *self._load(project))

    def _write(self, project, records, previous):
        path = self.library.metadata(project, create=True)
        if self._load(project)[1] != previous:
            raise AppError("Selections changed. Reload them before saving.", 409, "selection_conflict")
        payload = (json.dumps({"version": 1, "selections": records}, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".selections-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            # Revalidate the directory and destination immediately before replacement.
            if self.library.metadata(project) != path or self._load(project)[1] != previous:
                raise AppError("Selections changed during the save. Reload before saving.", 409, "selection_conflict")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return self._snapshot(project, records, hashlib.sha256(payload).hexdigest())

    def add(self, project, selection):
        with self.lock:
            valid_range(selection["start"], selection["end"])
            maximum = self.media_duration(project, selection["file"])
            if selection["end"] > maximum:
                raise AppError("The range ends after this video's duration.", 422, "invalid_range")
            records, revision = self._load(project)
            existing = next((row for row in records if row["id"] == selection["id"]), None)
            if existing:
                if existing == selection:
                    return self._snapshot(project, records, revision)
                raise AppError("This selection ID already exists.", 409, "selection_conflict")
            return self._write(project, records + [selection], revision)

    def capture(self, project, file, moment, identity):
        with self.lock:
            maximum = self.media_duration(project, file)
            if not math.isfinite(moment) or not 0 <= moment <= maximum:
                raise AppError("The capture time is outside this video.", 422, "invalid_range")
            return self.add(project, {"id": identity, "file": file, "start": max(0, moment - 15), "end": min(maximum, moment + 15)})

    def change(self, project, identity, expected, bounds=None):
        with self.lock:
            records, revision = self._load(project)
            if not expected or expected != revision:
                raise AppError("Selections changed. Reload them before saving.", 409, "selection_conflict")
            index = next((i for i, row in enumerate(records) if row["id"] == identity), None)
            if index is None:
                raise AppError("This selection no longer exists.", 404, "unavailable")
            if bounds is None:
                records.pop(index)
            else:
                valid_range(bounds["start"], bounds["end"])
                maximum = self.media_duration(project, records[index]["file"])
                if bounds["end"] > maximum:
                    raise AppError("The range ends after this video's duration.", 422, "invalid_range")
                records[index] = {**records[index], **bounds}
            return self._write(project, records, revision)
