"""Read movie duration by seeking over MP4 boxes, without decoding or copying media."""

import math
import struct

from .errors import AppError


def boxes(stream, start, end):
    position = start
    while position + 8 <= end:
        stream.seek(position)
        raw = stream.read(8)
        if len(raw) != 8:
            break
        size, kind = struct.unpack(">I4s", raw)
        header = 8
        if size == 1:
            extended = stream.read(8)
            if len(extended) != 8:
                break
            size = struct.unpack(">Q", extended)[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            break
        yield kind, position + header, position + size
        position += size


def duration(stream, size):
    for kind, start, end in boxes(stream, 0, size):
        if kind != b"moov":
            continue
        for child, payload, limit in boxes(stream, start, end):
            if child != b"mvhd":
                continue
            stream.seek(payload)
            raw = stream.read(min(32, limit - payload))
            if len(raw) >= 20 and raw[0] == 0:
                scale, ticks = struct.unpack(">II", raw[12:20])
                unknown = 0xFFFFFFFF
            elif len(raw) >= 32 and raw[0] == 1:
                scale, ticks = struct.unpack(">IQ", raw[20:32])
                unknown = 0xFFFFFFFFFFFFFFFF
            else:
                break
            value = ticks / scale if scale else 0
            if ticks != unknown and math.isfinite(value) and value > 0:
                return value
    raise AppError(
        "Cannot read this MP4's duration. Use a prepared, non-fragmented MP4 with a movie header.",
        422,
        "invalid_media",
    )
