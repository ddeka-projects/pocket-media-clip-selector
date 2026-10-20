"""Application assembly and command-line startup."""

import argparse
from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI
import uvicorn

from .api import register_routes
from .config import load_settings
from .controller import ControllerOwnership
from .library import Library
from .logging_setup import configure_logging
from .process_lock import ProcessLock
from .storage import ProjectStore


def create_app(settings=None, *, controller=None, lock_library=True):
    settings = settings or load_settings()
    library = Library(settings.working_directory)
    store = ProjectStore(library)
    controller = controller or ControllerOwnership()
    process_lock = ProcessLock(settings.working_directory)

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        if lock_library:
            process_lock.acquire()
        try:
            yield
        finally:
            controller.disconnect()
            process_lock.close()

    app = FastAPI(
        title="Pocket Media Clip Selector",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    app.state.controller = controller
    register_routes(app, settings, controller, store, library)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pocket Media Clip Selector local server")
    parser.add_argument(
        "--reload", action="store_true", help="Development only: reload Python code"
    )
    args = parser.parse_args(argv)
    configure_logging()
    try:
        settings = load_settings()
        logging.getLogger(__name__).info(
            "Starting on %s:%s; library: %s",
            settings.host,
            settings.port,
            settings.working_directory,
        )
        uvicorn.run(
            "pocket_media_clip_selector.app:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            workers=1,
            reload=args.reload,
            log_config=None,
            access_log=True,
            proxy_headers=False,
        )
        return 0
    except (Exception, KeyboardInterrupt):
        logging.getLogger(__name__).exception("The server could not start or stopped unexpectedly")
        return 1
