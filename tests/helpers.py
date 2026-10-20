from pathlib import Path
import struct


def box(kind, payload, *, extended=False):
    return (
        struct.pack(">I4sQ", 1, kind, len(payload) + 16)
        if extended
        else struct.pack(">I4s", len(payload) + 8, kind)
    ) + payload


def mp4_bytes(seconds=120.5, *, version=0, tail=False, extended=False):
    scale = 1000
    if version == 0:
        header = b"\0" * 12 + struct.pack(">II", scale, round(seconds * scale))
    else:
        header = b"\1\0\0\0" + b"\0" * 16 + struct.pack(">IQ", scale, round(seconds * scale))
    movie = box(b"moov", box(b"mvhd", header), extended=extended)
    payload = box(b"mdat", bytes(range(256)) * 5)
    filetype = box(b"ftyp", b"isom\0\0\0\0isommp42")
    return filetype + (payload + movie if tail else movie + payload)


def make_project(
    root: Path, name="A Show – 日本語", file="[Some Group] Episode #1 & café.mp4", seconds=120.5
):
    project = root / name
    project.mkdir(exist_ok=True)
    (project / file).write_bytes(mp4_bytes(seconds))
    return name, file
