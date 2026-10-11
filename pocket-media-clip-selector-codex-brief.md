# Pocket Media Clip Selector - Codex Implementation Brief

**Repository/application:** `ddeka-projects/pocket-media-clip-selector`  
**Target:** MVP v1.0  
**Platform:** Windows PC server; iPhone Safari client  
**Status:** Product and implementation handoff. Please build a working MVP, not just a plan or scaffold.

## 1. Purpose

This is a personal, local-first tool for finding and recording interesting scenes in movies and television episodes. The user enjoys reviewing footage on an iPhone but dislikes having to find all those moments again while sitting at a Windows PC to edit. Move the **scene-finding and rough selection** work onto the phone.

A successful MVP lets the user browse locally stored video, scrub through it, save a moment or an IN/OUT range, and reliably return to those selections later. The source videos remain untouched. **The MVP does not produce final clips**; extraction, concatenation, and Premiere integration are later phases.

Favor a small, dependable, pleasant-to-use app over an elaborate architecture. The user expects to refine the experience after testing it on a real iPhone.

## 2. Existing work to inspect before implementation

These are the user's own repositories. Reuse sensible patterns rather than copying their entire codebases:

- [pocket-manga-editor](https://github.com/ddeka-projects/pocket-manga-editor): best example of a **single active browser-page/controller lease**, including iPhone background/resume handling and an "open elsewhere" screen; also has Windows Task Scheduler scripts.
- [pocket-entertainment-catalog](https://github.com/ddeka-projects/pocket-entertainment-catalog): in-memory 5-second-heartbeat / 15-second-expiry lease, safe JSON/JSONL persistence, and **Windows user-logon** task setup.
- [pocket-media-manager](https://github.com/ddeka-projects/pocket-media-manager): Python/FastAPI-style PC helper, local media serving, development runner, and scheduled server startup.

**Preferred combination:** Manga Editor's exclusive-page behavior, Catalog's user-logon startup and safe file writes, and the simplest appropriate media-streaming stack. Keep Clip Selector materially smaller than these projects.

## 3. Environment, files, and boundaries

A **separate, already-built media processor** prepares downloads for editing/streaming. Do not rebuild or integrate that processor into this app. Its outputs are H.264 MP4 videos with compatible audio, generally 1080p or below. A source originally in 4K may already have been downscaled to 1080p. There is no need for 720p proxies, live transcoding, conversion, or FFmpeg in the web app MVP.

A `.env` file points to a **Windows** working directory:

```dotenv
WORKING_DIR=D:\MediaProjects
HOST=0.0.0.0
PORT=8767
```

The port is a suggested default; make it configurable. Keep the app's repository/code **outside** `WORKING_DIR`.

Directory convention:

```text
D:\MediaProjects\
  A Show - Season 1\                  <- project
    [Some Group] Episode One.mp4      <- eligible, processed video
    totally-arbitrary-name.mp4        <- eligible, processed video
    Source\                           <- original downloads; ignore
      [Some Group] Episode One.mkv
    .clipselector\                    <- project metadata; ignore as media
      manifest.json                   <- media processor may own this
      selections.json                 <- Clip Selector owns this
  An Example Movie\                  <- another project
    movie.mp4
```

**Scanner contract:**

- Each immediate child **directory** of `WORKING_DIR` is a project. Ignore loose files in the working directory (the processor's scripts may live there).
- Only `.mp4` files directly inside a project directory are playable. Never recurse into `Source/`, `.clipselector/`, or any other subfolder. Ignore other extensions and subdirectories.
- Preserve exact user filenames, including spaces, punctuation, and Unicode. No `S01E01` or other filename convention; a project can be one movie or many episodes.
- Sort projects and media alphabetically ascending, case-insensitively, with a deterministic tie-breaker.
- Do **not** require `manifest.json` to exist, and do not write to it. A project with manually prepared MP4 files must also work.
- Saved references to missing/renamed files should show as unavailable, not silently attach to a different file.

## 4. Core mobile workflows

### A. Browse

Open a local-network URL in Safari on the iPhone. See a simple project library, choose a project, then choose one of its processed MP4s. Provide an easy way back and previous/next media navigation in sorted order.

### B. Watch and seek

- Use an **inline** HTML5 player (`playsinline`), designed primarily for comfortable **portrait** iPhone use.
- Show current time/duration, a usable scrubber, play/pause, and prominent skip buttons for -15, -5, +5, +15 seconds.
- Offer playback speeds **0.25x, 0.5x, 1x, 2x, 3x**. Use the browser's playback-rate API; test or gracefully handle an extreme rate that Safari may not honor. Do not silently show a speed the player did not accept.
- Prioritize quick seeking and a clear, touch-friendly, one-handed layout. Native video plumbing is fine; avoid a big video-editor timeline.

### C. Quick Capture (primary interaction)

A large **Capture Moment** button saves the range from **15 seconds before** to **15 seconds after** the current playback time, clamped to the media duration. **Save immediately and continue playback**; briefly confirm success without interrupting viewing. Use fractional-second timestamps from `video.currentTime`. Overlapping captures may remain separate; do not build automatic merging yet.

### D. Manual IN/OUT

Provide **Mark IN**, **Mark OUT**, then **Save Range**, plus a way to cancel/reset an unfinished selection. Validate that IN is earlier than OUT. This complements quick capture for longer or more deliberately selected scenes.

### E. Saved selections

A simple view shows all selections for the current project, grouped/ordered by media filename then timestamp. Allow the user to:

- Tap a selection to return to the relevant video/time and replay it.
- Adjust start and end timestamps (sensible touch controls or small nudges are fine).
- Delete an unwanted selection safely.

Every confirmed add/edit/delete saves to the **PC immediately**. Selections must survive closing Safari, reloading, and restarting the server. There is no user account or sync service.

These may be implemented as three screens/views: **Project Library**, **Player**, and **Selections**. Visual polish matters for mobile usability, but avoid unrelated functionality.

## 5. Selection persistence and file safety

Each project stores its own selection data at:

`<WORKING_DIR>/<PROJECT>/.clipselector/selections.json`

A simple, versioned JSON format is sufficient. For example:

```json
{
  "version": 1,
  "selections": [
    {
      "id": "unique-stable-id",
      "file": "[Some Group] Episode One.mp4",
      "start": 502.25,
      "end": 519.75
    }
  ]
}
```

Codex can refine the schema if useful. Timestamps are seconds, with fractional precision. Store **relative file identity**, not absolute machine-specific paths. Create `.clipselector` and the JSON file lazily if missing.

- Serialize server-side mutations, validate the selected project/media paths and ranges, and write through a temporary file plus atomic replacement. Never truncate or corrupt the old file on failed writes.
- Do not let URL input escape the configured library via `..`, symlinks, junctions, or arbitrary absolute paths.
- Do not rename, move, overwrite, modify, or delete the MP4s, `Source/`, or the processor's manifest.
- If a request cannot be saved, **show an error**; never claim it was saved successfully.
- No external database, Git synchronization, or cloud storage.

## 6. Exclusive controller / multiple tabs

Use the **exclusive active-page model from Pocket Manga Editor**, not an editing lock that only activates for a form.

- The first browser page claims one **in-memory server-side lease for the entire app**. Only this page has normal app/controller access. A second tab or device shows **"Clip Selector is open elsewhere"** and can retry instead of entering a competing editing session.
- Heartbeat approximately every **5 seconds**; lease expires after approximately **15 seconds** without renewal. Best-effort release on page close/navigation.
- Distinguish each **page instance**, not only the device/browser, so a duplicated tab cannot share editing authority.
- Handle Safari suspension, app switching, and reconnection: on return, attempt to reclaim or renew; if another page acquired the lease, disallow stale writes and show the occupied state.
- **All selection mutations** must be authorized server-side using the live page lease. Never rely on a front-end-only lock. Do not persist lease state in JSON.
- Video stream requests can be read-only without custom lease headers, since the HTML video element cannot reliably attach those headers.

Run **one server process / one worker**. Prevent accidental duplicate production instances (Task Scheduler `IgnoreNew` and a fixed port; add a simple process/data lock if needed). There is no need for a multi-writer distributed system.

## 7. Local video delivery

Stream the existing top-level MP4 directly from the Windows machine to Safari over the trusted home LAN. Do not upload, transcode, or copy whole files into the phone's storage.

**Correct HTTP byte-range behavior is essential** for Safari seeking: support `Range` / `206 Partial Content`, suitable headers, proper MIME type, and efficient file streaming rather than loading whole episodes into RAM. Accommodate browser `HEAD` requests if needed. Guard all media routes against unsafe paths.

Use the simplest solid Python solution. **FastAPI + Uvicorn + vanilla HTML/CSS/JS** is an acceptable default, but choose a lighter implementation if it demonstrably improves reliability/simplicity. No frontend build pipeline is required.

## 8. Windows-only launch and deployment

Model the operations after the referenced repositories, but keep them straightforward:

- `scripts/bootstrap-windows.ps1`: install/create local Python environment and prepare `.env.example` -> `.env` as needed.
- `scripts/run-dev.ps1`: foreground development server, optionally with automatic code reload; useful diagnostics.
- `scripts/run-server.ps1`: non-reloading normal server with logs.
- `scripts/install-startup-task.ps1`: Windows Task Scheduler **at current-user logon**, not as `SYSTEM`; starts immediately, runs without a visible console, ignores duplicate task instances, and retries after unexpected exits.
- `scripts/remove-startup-task.ps1`: stop and unregister the task; do not delete media or selections.

Configure network access for **Private-profile / LocalSubnet only** when setting up Windows Firewall. No public internet exposure, router port forwarding, accounts, or remote-hosting features. Show the local network URL in documentation and on manual startup, and save operational logs outside `WORKING_DIR`. The PC must be awake and running to serve videos.

The ordinary Windows user should retain access to the media paths. Use normal Windows absolute path handling, including drive letters, spaces, and Unicode. No other OS support is required.

## 9. Deliberately outside v1.0

Do **not** build any of the following yet: media downloading or conversion; 720p proxy creation; FFmpeg trimming/concatenation; final exports to HDD; Premiere timeline generation; social-media integrations; AI scene detection; cloud access; multi-user accounts; project analytics; elaborate metadata; external databases. Playback-resume history, looping, and advanced selection editing can wait unless trivially helpful.

## 10. Definition of done

Deliver a runnable repository with clear Windows setup/operation documentation and focused automated tests. At minimum verify:

1. Project/media discovery honors the immediate-child/top-level-MP4 rules and arbitrary names.
2. Byte-range streaming works, including requests into the middle of a video and invalid ranges.
3. A phone can open the app, play/seek video inline, and use the requested speed options (report any untested/unsupported iOS rate honestly).
4. Quick Capture saves the expected clamped range **without pausing**, and IN/OUT saves a deliberate range.
5. Selections can be viewed, adjusted, deleted, and remain after browser/server restart.
6. A second tab cannot mutate while another page controls the app; expiry/reconnect behave safely.
7. Writes are atomic and path validation blocks traversal; source media and `manifest.json` are never modified.
8. Manual development startup and Windows user-logon startup paths are documented and implemented.

Test server-side behavior automatically where possible. Include a short **real-iPhone manual test checklist** for anything Codex cannot verify itself, especially seeking, Safari lifecycle behavior, and playback speeds. Be explicit about any remaining limitations.

## 11. Execution instruction for Codex

**Implement this MVP end-to-end in `pocket-media-clip-selector` (create/initialize the new repository if needed).** Inspect the referenced repositories first for reusable conventions, make reasonable minor engineering decisions independently, and avoid expanding the scope. Create the code, tests, `.env.example`, Windows scripts, and README. Run the automated checks available in your environment, fix failures, and summarize what was implemented, what was tested, and exactly what still requires testing on the user's Windows PC/iPhone.
