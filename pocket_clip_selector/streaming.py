"""Bounded file streaming with Safari's single byte ranges and HEAD support."""

from email.utils import formatdate
import re

from fastapi.responses import Response, StreamingResponse


class OpenFileResponse(StreamingResponse):
    def __init__(self, stream, start, length, **kwargs):
        self.stream = stream

        def chunks():
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(256 * 1024, remaining))
                if not chunk:
                    raise OSError("Media was truncated during streaming.")
                remaining -= len(chunk)
                yield chunk

        super().__init__(chunks(), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()


def media_response(library, project, file, request):
    stream, info = library.open_media(project, file)
    size = info.st_size
    etag = f'"{info.st_dev:x}-{info.st_ino:x}-{info.st_size:x}-{info.st_mtime_ns:x}"'
    modified = formatdate(info.st_mtime, usegmt=True)
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(size), "ETag": etag,
               "Last-Modified": modified, "Cache-Control": "private, no-cache",
               "Content-Disposition": "inline"}
    start, end = 0, size - 1
    status = 200
    raw = request.headers.get("range") if request.method == "GET" else None
    if_range = request.headers.get("if-range")
    if if_range and if_range not in (etag, modified):
        raw = None
    # HTTP permits ignoring unsupported units or multiple ranges; never build a
    # large multipart response for a local episode. Safari uses a single range.
    if raw and raw.startswith("bytes=") and "," not in raw:
        match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", raw)
        valid = bool(match and any(match.groups())) and size > 0
        if valid:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
                valid = start < size and end >= start
            else:
                length = int(last)
                valid = length > 0
                start, end = max(0, size - length), size - 1
        if not valid:
            stream.close()
            return Response(status_code=416, headers={**headers, "Content-Length": "0", "Content-Range": f"bytes */{size}"}, media_type="video/mp4")
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
    if request.method == "HEAD" or size == 0:
        stream.close()
        return Response(status_code=status, headers=headers, media_type="video/mp4")
    return OpenFileResponse(stream, start, end - start + 1, status_code=status, headers=headers, media_type="video/mp4")
