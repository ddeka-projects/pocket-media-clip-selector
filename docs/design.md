# Application design

Pocket Media Clip Selector is one local Python web server and a mobile-friendly browser interface. The Windows PC owns all project folders and saved bookmarks. The phone sends ordinary HTTP requests; it does not keep an offline database or queue saves. Each repository in the Pocket workspace remains independently installable.

## Modules and startup

| Module | Responsibility |
| --- | --- |
| `__main__.py` | Delegate `python -m pocket_media_clip_selector` to the application entry point |
| `app.py` | Assemble FastAPI, storage, browser control, the server lifetime guard, and Uvicorn startup |
| `api.py` | Validate request bodies, route operations, serialize errors, and deliver `/static/` assets |
| `config.py` / `env.py` | Load and validate settings using the shared literal `.env` convention |
| `controller.py` | One explicit controlling browser page, including safe takeover |
| `process_lock.py` | One running server per canonical working-directory path |
| `storage.py` | Project/source/bookmark operations, revisions, validation, and atomic JSON saves |
| `library.py` | Discover direct project/media children and enforce filesystem boundaries |
| `streaming.py` / `mp4.py` | Bounded MP4 byte streaming and duration inspection |
| `errors.py` | Stable application error codes, status, and messages |
| `logging_setup.py` / `health.py` | Bounded logs and readiness with application/process identity |
| `static/` | Browser UI, timestamp handling, playback helpers, styles, and Home Screen assets |

The shared concerns use the same small modules and interfaces as the sibling apps. Project-specific behavior stays local; no sibling repository is needed at runtime.

Windows setup creates `.venv` and starts the server under the signed-in user's normal privileges. Task Scheduler runs console-free Python and tracks the actual server process. Foreground troubleshooting uses the same application with console output. Logs, including startup failures, go to `logs/server.log`, rotating at 5 MiB with three backups.

The server acquires its lifetime guard before accepting requests. A second server using the same library fails even on another port or from another checkout. The operating system releases the guard after normal exit or a crash. This protection is separate from browser ownership and safe file writes.

## Configuration

The current contract is [`.env.example`](../.env.example):

- `POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY`: required absolute path to an existing local media directory, separate from the repository.
- `POCKET_MEDIA_CLIP_SELECTOR_HOST`: bind address, normally `0.0.0.0`.
- `POCKET_MEDIA_CLIP_SELECTOR_PORT`: TCP port, normally `8767`.

`Settings` and `load_settings(env_file=None, *, environ=None)` provide the application settings. UTF-8 `.env` files accept an optional BOM and matching quotes. Values are literal, including Windows backslashes and `$`; there is no expansion. Duplicate assignments and malformed quoting are rejected. Real environment variables override file values. Configuration and media paths do not depend on the launcher's working directory. Links, junctions, and reparse points in the library path are rejected.

## One controlling page

The first page claims an unoccupied controller. Other pages show **Take Control** before browsing project data or editing. Claims and explicit takeover return a random token; data requests carry `X-Page-Id` and `X-Controller-Token`.

Control lasts until deliberate release, takeover, or server restart. It has no heartbeat, expiry, or background polling. Tokens and page identities stay in memory, so a full reload creates another page identity. Browser local storage remembers only the last project/source names.

The controller lock covers complete authorized operations. A takeover waits for an accepted save to finish, then rejects the old token. The old page notices on its next ordinary request and keeps its draft/frame while offering Take Control. Takeover refreshes data without resubmitting a save.

`Exit Editor` releases control and pauses playback only after confirmation. Static assets and `/health` are public. Direct `/media` streaming is independent of ownership so transfer does not interrupt an already loaded player; the normal application still gates browsing and controls.

## Storage and uncertain saves

Each immediate child of the configured library is a project. Its first source creates `.clipselector/project.json`, using schema version 2. Named sources contain optional exact MP4 filenames and bookmarks with stable IDs and timestamps. The independent processor's manifest and source media remain untouched.

Mutations serialize a fresh read, validate stored data, write a temporary file, flush/fsync, recheck the revision, and atomically replace metadata. `If-Match` protects destructive edits from stale snapshots. Corrupt or unsupported data is reported rather than replaced with empty data.

Replaying the same bookmark ID with identical data is safe. Reusing it for different data is rejected. Quick Log and Watch retain an unconfirmed entry in page memory and let the user explicitly retry or refresh to verify it. No automatic retry claims a save succeeded. Back up `.clipselector/project.json` with its project; this app does not create a separate backup history.

## Request safety and errors

Requests must come from a private, loopback, or link-local peer and use a permitted local Host authority. API origins must match this server; cross-site mutations are rejected. Typed request bodies reject unexpected fields and invalid values. Library access refuses traversal, links, reparse points, and files outside direct supported locations. Responses set a restrictive content security policy and prevent MIME sniffing.

Errors use `{ "ok": false, "error": { "code": "...", "message": "..." } }`, with optional application details. The browser gets a useful message, while unexpected and filesystem failures are recorded in the log. This is a trusted home-LAN application without accounts or public hosting.

`/health` identifies both the package and the current process instance. Installation and restart scripts verify a fresh instance, preventing an old or unrelated listener from being mistaken for a successful restart.

See the [README](../README.md) for setup, current workflows, verification commands, and Windows/iPhone checks.
