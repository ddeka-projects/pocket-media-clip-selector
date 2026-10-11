import argparse
import logging
import logging.handlers
import socket

import uvicorn

from .config import REPOSITORY, load_settings


def run():
    parser = argparse.ArgumentParser(description="Pocket Media Clip Selector local server")
    parser.add_argument("--reload", action="store_true", help="Development only: reload Python code")
    args = parser.parse_args()
    settings = load_settings()
    logs = REPOSITORY / "logs"
    logs.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(logs / "server.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for name in ("uvicorn", "pocket_clip_selector"):
        logging.getLogger(name).addHandler(handler)
    print(f"PC: http://127.0.0.1:{settings.port}", flush=True)
    if settings.host in ("0.0.0.0", "::"):
        try:
            addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET) if not entry[4][0].startswith("127.")})
        except OSError:
            addresses = []
        for address in addresses:
            print(f"iPhone (same Wi-Fi): http://{address}:{settings.port}", flush=True)
        if not addresses:
            print(f"iPhone: http://<PC IPv4 address from ipconfig>:{settings.port}", flush=True)
    else:
        print(f"Listening on http://{settings.host}:{settings.port}", flush=True)
    print(f"Library: {settings.working_dir}\nLogs: {logs / 'server.log'}", flush=True)
    uvicorn.run("pocket_clip_selector.api:create_app", factory=True, host=settings.host,
                port=settings.port, workers=1, reload=args.reload, reload_dirs=[str(REPOSITORY / "pocket_clip_selector")] if args.reload else None,
                log_config=None, access_log=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
