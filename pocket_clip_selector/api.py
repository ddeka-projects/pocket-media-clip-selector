from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr

from .config import Settings, load_settings
from .errors import AppError
from .controller import ControllerOwnership
from .library import Library
from .process_lock import ProcessLock
from .storage import SelectionStore
from .streaming import media_response

STATIC = Path(__file__).parent / "static"
Seconds = Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]
Identity = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Body):
    page_id: Identity


class Owner(Page):
    token: StrictStr


class Bounds(Body):
    start: Seconds
    end: Seconds


class NewSelection(Bounds):
    id: Identity
    file: StrictStr


class Capture(Body):
    id: Identity
    file: StrictStr
    time: Seconds


def create_app(settings: Settings | None = None, *, controller=None, lock_library=True):
    settings = settings or load_settings()
    library = Library(settings.working_dir)
    store = SelectionStore(library)
    controller = controller or ControllerOwnership()
    process_lock = ProcessLock(settings.working_dir)

    @asynccontextmanager
    async def lifespan(app):
        if lock_library:
            process_lock.acquire()
        try:
            yield
        finally:
            process_lock.close()

    app = FastAPI(title="Pocket Media Clip Selector", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.controller = controller

    def error_response(error):
        return JSONResponse({"error": {"code": error.code, "message": str(error)}}, status_code=error.status)

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return error_response(error)

    @app.exception_handler(OSError)
    async def filesystem_error(request, error):
        logging.getLogger("uvicorn.error").exception("Filesystem operation failed")
        return error_response(AppError("The PC could not read or save this file. Check directory permissions, disk space, and the server log. No save was confirmed.", 500, "storage_error"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return error_response(AppError("Invalid request. Times must be finite numbers and filenames must be exact.", 422, "invalid_request"))

    @app.middleware("http")
    async def local_requests(request, call_next):
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if request.url.path.startswith("/api/") and origin and origin != expected_origin:
            return error_response(AppError("Open the app from this server's own local URL.", 403, "foreign_origin"))
        response = await call_next(request)
        if not request.url.path.startswith("/media"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    def access(request):
        return controller.authorized(request.headers.get("x-page-id"), request.headers.get("x-controller-token"))

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/assets/{name}")
    def asset(name: str):
        allowed = {"app.js": "text/javascript", "player.js": "text/javascript", "styles.css": "text/css", "icon.svg": "image/svg+xml",
                   "manifest.webmanifest": "application/manifest+json", "apple-touch-icon.png": "image/png"}
        if name not in allowed:
            raise AppError("Asset not found.", 404, "unavailable")
        return FileResponse(STATIC / name, media_type=allowed[name])

    @app.get("/health")
    def health():
        return {"ok": True, "version": "1.0"}

    @app.post("/api/controller/claim")
    def claim(body: Page):
        return controller.claim(body.page_id)

    @app.post("/api/controller/takeover")
    def takeover(body: Page):
        return controller.claim(body.page_id, takeover=True)

    @app.post("/api/controller/release")
    def release(body: Owner):
        controller.release(body.page_id, body.token)
        return {"released": True}

    @app.get("/api/projects")
    def projects(request: Request):
        with access(request):
            return {"projects": library.projects()}

    @app.get("/api/project")
    def project(request: Request, project: str):
        with access(request):
            return {"name": library.project(project).name, "media": library.files(project)}

    @app.get("/api/media-info")
    def media_info(request: Request, project: str, file: str):
        with access(request):
            return {"duration": store.media_duration(project, file)}

    @app.get("/api/selections")
    def selections(request: Request, project: str):
        with access(request):
            return store.list(project)

    @app.post("/api/selections", status_code=201)
    def add_selection(request: Request, project: str, body: NewSelection):
        with access(request):
            return store.add(project, body.model_dump())

    @app.post("/api/selections/capture", status_code=201)
    def capture(request: Request, project: str, body: Capture):
        with access(request):
            return store.capture(project, body.file, body.time, body.id)

    @app.patch("/api/selections/{identity}")
    def edit_selection(request: Request, identity: str, project: str, body: Bounds):
        with access(request):
            return store.change(project, identity, request.headers.get("if-match"), body.model_dump())

    @app.delete("/api/selections/{identity}")
    def delete_selection(request: Request, identity: str, project: str):
        with access(request):
            return store.change(project, identity, request.headers.get("if-match"))

    @app.api_route("/media", methods=["GET", "HEAD"])
    def media(request: Request, project: str, file: str):
        return media_response(library, project, file, request)

    return app
