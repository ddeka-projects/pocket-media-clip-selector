"""Named sources and single-time bookmarks, with serialized atomic project writes."""

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

SCHEMA_VERSION = 2
MAX_SECONDS = 3_599_999.999  # Up to 999 hours; shared with the client parser.
ID_PATTERN = r"[A-Za-z0-9_-]{16,128}"


def source_name(value):
    if not isinstance(value, str):
        raise AppError("Give the source a name.", 422, "invalid_source_name")
    name = value.strip()
    if not name or len(name) > 100 or any(ord(char) < 32 or 127 <= ord(char) < 160 or 0xD800 <= ord(char) <= 0xDFFF for char in name):
        raise AppError("Source names must contain 1–100 characters without control characters.", 422, "invalid_source_name")
    return name


def episode_number(name):
    match = re.fullmatch(r"(?:episode|ep)\s*(\d+)", " ".join(name.split()).casefold(), re.ASCII)
    return int(match[1]) if match else None


def source_key(name):
    normalized = " ".join(source_name(name).split()).casefold()
    number = episode_number(normalized)
    return ("episode", number) if number is not None else ("name", normalized)


def next_episode(names):
    numbers = {number for name in names if (number := episode_number(name)) is not None}
    number = max(numbers, default=0) + 1
    label = f"Episode {number:02d}"
    if len(label) > 100:
        number = 1
        while number in numbers:
            number += 1
        label = f"Episode {number:02d}"
    return label


def following_episode(name, names):
    number = episode_number(name)
    label = f"Episode {number + 1:02d}" if number is not None else ""
    return label if label and len(label) <= 100 else next_episode(names)


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def valid_time(value):
    if type(value) not in (int, float) or not 0 <= value <= MAX_SECONDS or not math.isfinite(value):
        raise AppError("Bookmark time must be finite seconds between 0 and 999:59:59.999.", 422, "invalid_time")


def valid_media_name(file):
    if file is not None:
        validate_name(file)
        if Path(file).suffix.lower() != ".mp4":
            raise AppError("Choose an exact top-level MP4 filename.", 400, "unsafe_path")


class ProjectStore:
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
        if not payload and not path.exists():
            return {"version": SCHEMA_VERSION, "sources": {}}, revision
        try:
            data = json.loads(payload, object_pairs_hook=json_object)
            if (type(data) is not dict or set(data) != {"version", "sources"}
                    or type(data["version"]) is not int or data["version"] != SCHEMA_VERSION
                    or type(data["sources"]) is not dict):
                raise ValueError("unsupported project format")
            keys, identities = set(), set()
            for name, source in data["sources"].items():
                if source_name(name) != name or source_key(name) in keys:
                    raise ValueError("duplicate or invalid source")
                keys.add(source_key(name))
                if type(source) is not dict or set(source) != {"media_file", "bookmarks"} or type(source["bookmarks"]) is not list:
                    raise ValueError("invalid source")
                valid_media_name(source["media_file"])
                for bookmark in source["bookmarks"]:
                    if type(bookmark) is not dict or set(bookmark) != {"id", "time"}:
                        raise ValueError("invalid bookmark")
                    identity = bookmark["id"]
                    if not isinstance(identity, str) or not re.fullmatch(ID_PATTERN, identity) or identity in identities:
                        raise ValueError("invalid or duplicate bookmark id")
                    identities.add(identity)
                    valid_time(bookmark["time"])
            return data, revision
        except (ValueError, KeyError, TypeError, AppError, OverflowError) as error:
            raise AppError("Project JSON is damaged or uses an unsupported format. The file was left untouched; restore a valid backup.", 500, "invalid_storage") from error

    def _snapshot(self, project, data, revision):
        sources = [{"name": name, "media_file": row["media_file"],
                    "next_episode_name": following_episode(name, data["sources"]),
                    "available": row["media_file"] is not None and self.library.available(project, row["media_file"]),
                    "bookmarks": sorted(row["bookmarks"], key=lambda mark: (mark["time"], mark["id"]))}
                   for name, row in sorted(data["sources"].items(), key=lambda item: sort_key(item[0]))]
        return {"name": project, "revision": revision, "sources": sources,
                "source_count": len(sources), "bookmark_count": sum(len(row["bookmarks"]) for row in sources),
                "next_source_name": next_episode(data["sources"]), "media": self.library.files(project)}

    def list(self, project):
        with self.lock:
            return self._snapshot(project, *self._load(project))

    def projects(self):
        with self.lock:
            rows = self.library.projects()
            for row in rows:
                try:
                    snapshot = self.list(row["name"])
                    row.update({key: snapshot[key] for key in ("source_count", "bookmark_count")})
                except (AppError, OSError) as error:
                    row.update(source_count=None, bookmark_count=None, error=str(error))
            return rows

    def _write(self, project, data, previous):
        path = self.library.metadata(project, create=True)
        if self._load(project)[1] != previous:
            raise AppError("Project changed. Refresh it before saving.", 409, "project_conflict")
        payload = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".project-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            if self.library.metadata(project) != path or self._load(project)[1] != previous:
                raise AppError("Project changed during the save. Refresh before saving.", 409, "project_conflict")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return self._snapshot(project, data, hashlib.sha256(payload).hexdigest())

    def _expected(self, project, expected):
        data, revision = self._load(project)
        if not expected or expected != revision:
            raise AppError("Project changed. Refresh it before saving.", 409, "project_conflict")
        return data, revision

    def create(self, name):
        with self.lock:
            project = self.library.create_project(name)
            return self.list(project)

    def _source(self, data, name):
        if name not in data["sources"]:
            raise AppError("This source no longer exists. Refresh the project.", 404, "unavailable")
        return data["sources"][name]

    def _unique(self, data, name, exclude=None):
        for existing in data["sources"]:
            if existing != exclude and source_key(existing) == source_key(name):
                raise AppError(f"{existing} already exists.", 409, "source_exists", {"source": existing})

    def add_source(self, project, name, file, expected):
        with self.lock:
            data, revision = self._expected(project, expected)
            name = source_name(name)
            self._unique(data, name)
            valid_media_name(file)
            if file is not None:
                self.library.media(project, file)
            data["sources"][name] = {"media_file": file, "bookmarks": []}
            return self._write(project, data, revision)

    def change_source(self, project, original, changes, expected):
        with self.lock:
            data, revision = self._expected(project, expected)
            source = self._source(data, original)
            name = source_name(changes.get("name", original))
            file = changes.get("media_file", source["media_file"])
            self._unique(data, name, exclude=original)
            valid_media_name(file)
            # Preserve an unchanged missing association so renames still work.
            if file is not None and file != source["media_file"]:
                self.library.media(project, file)
            del data["sources"][original]
            data["sources"][name] = {**source, "media_file": file}
            return self._write(project, data, revision)

    def delete_source(self, project, name, expected):
        with self.lock:
            data, revision = self._expected(project, expected)
            self._source(data, name)
            del data["sources"][name]
            return self._write(project, data, revision)

    def add_bookmark(self, project, name, bookmark):
        with self.lock:
            valid_time(bookmark["time"])
            if not isinstance(bookmark["id"], str) or not re.fullmatch(ID_PATTERN, bookmark["id"]):
                raise AppError("Invalid bookmark identity.", 422, "invalid_request")
            data, revision = self._load(project)
            source = self._source(data, name)
            for other, row in data["sources"].items():
                existing = next((mark for mark in row["bookmarks"] if mark["id"] == bookmark["id"]), None)
                if existing:
                    if other == name and existing == bookmark:
                        return self._snapshot(project, data, revision)
                    raise AppError("This bookmark ID already exists with different data.", 409, "bookmark_conflict")
            source["bookmarks"].append(bookmark)
            return self._write(project, data, revision)

    def change_bookmark(self, project, name, identity, expected, time=None):
        with self.lock:
            data, revision = self._expected(project, expected)
            records = self._source(data, name)["bookmarks"]
            index = next((i for i, row in enumerate(records) if row["id"] == identity), None)
            if index is None:
                raise AppError("This bookmark no longer exists.", 404, "unavailable")
            if time is None:
                records.pop(index)
            else:
                valid_time(time)
                records[index] = {**records[index], "time": time}
            return self._write(project, data, revision)
