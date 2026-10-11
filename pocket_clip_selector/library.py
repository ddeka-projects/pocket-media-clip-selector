"""Nonrecursive discovery and strict filesystem boundaries, including reparse points."""

import os
from pathlib import Path
import stat

from .errors import AppError


def sort_key(name):
    return (name.casefold(), name)


def validate_name(name):
    if (not isinstance(name, str) or not name or name in (".", "..")
            or any(char in name for char in ("/", "\\", ":", "\0"))
            or name.endswith((".", " "))):
        raise AppError("Use an exact top-level project or MP4 filename.", 400, "unsafe_path")
    return name


def reject_link(path: Path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise AppError("Links and Windows reparse points are not allowed in the library.", 400, "unsafe_path")
    return info


class Library:
    def __init__(self, root: Path):
        self.root = root.absolute()
        self.check_root()

    def check_root(self):
        # Check ancestors too: resolve() alone would silently accept a junction.
        for path in (*reversed(self.root.parents), self.root):
            reject_link(path)
        if not self.root.is_dir():
            raise AppError("The media working directory is unavailable.", 503, "library_unavailable")

    def child(self, parent, name, *, directory=False, missing=False):
        validate_name(name)
        self.check_root()
        target = parent / name
        try:
            info = reject_link(target)
        except FileNotFoundError:
            if missing:
                return target
            raise AppError("This project or media file is unavailable.", 404, "unavailable") from None
        if directory and not stat.S_ISDIR(info.st_mode) or not directory and not stat.S_ISREG(info.st_mode):
            raise AppError("Expected a regular directory or file.", 400, "unsafe_path")
        if target.resolve().parent != parent.resolve() or not target.resolve().is_relative_to(self.root.resolve()):
            raise AppError("The requested path is outside the library.", 400, "unsafe_path")
        # Windows is case-insensitive. Saved identity must still match the exact spelling.
        if not any(entry.name == name for entry in parent.iterdir()):
            raise AppError("This exact filename is unavailable.", 404, "unavailable")
        return target

    def project(self, name):
        return self.child(self.root, name, directory=True)

    def media(self, project, file):
        validate_name(file)
        if Path(file).suffix.lower() != ".mp4":
            raise AppError("Only top-level MP4 files are playable.", 400, "unsafe_path")
        return self.child(self.project(project), file)

    def files(self, project):
        folder = self.project(project)
        result = []
        for path in folder.iterdir():
            if path.suffix.lower() != ".mp4":
                continue
            try:
                target = self.child(folder, path.name)
                result.append({"name": target.name, "bytes": target.stat().st_size})
            except (AppError, FileNotFoundError):
                continue
        return sorted(result, key=lambda item: sort_key(item["name"]))

    def projects(self):
        self.check_root()
        result = []
        for path in self.root.iterdir():
            if not path.is_dir():
                continue
            try:
                self.project(path.name)
                result.append({"name": path.name, "media_count": len(self.files(path.name))})
            except (AppError, FileNotFoundError):
                continue
        return sorted(result, key=lambda item: sort_key(item["name"]))

    def available(self, project, file):
        try:
            self.media(project, file)
            return True
        except (AppError, OSError):
            return False

    def metadata(self, project, *, create=False):
        folder = self.project(project)
        meta = self.child(folder, ".clipselector", directory=True, missing=True)
        if create:
            meta.mkdir(exist_ok=True)
        if meta.exists():
            meta = self.child(folder, ".clipselector", directory=True)
            return self.child(meta, "selections.json", missing=True)
        return meta / "selections.json"

    def open_media(self, project, file):
        target = self.media(project, file)
        before = reject_link(target)
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            after = os.fstat(descriptor)
            if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise AppError("Media changed while opening it. Try again.", 409, "media_changed")
            self.media(project, file)
            return os.fdopen(descriptor, "rb"), after
        except BaseException:
            os.close(descriptor)
            raise
