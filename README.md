# Pocket Media Clip Selector

Keep moments from any player in **project → named source → bookmarks**. While watching in VLC, open Quick Log, type a time such as `1742`, and save `17:42` on your Windows PC. No local media is required. Later, link a prepared MP4 to the same source and inspect those moments in the landscape player. Precise editing stays in Premiere Pro.

The app uses Python, FastAPI, Uvicorn, and vanilla HTML/CSS/JavaScript. It has no frontend build step, database, accounts, cloud service, media conversion, or final clip export. The PC must stay awake and the server must be running.

## Windows setup

You need Windows PowerShell 5.1+, Python 3.11+ from [python.org](https://www.python.org/downloads/windows/). For local playback, use prepared H.264 MP4 videos with Safari-compatible audio. Use an ordinary Windows account that can create project folders and write their metadata, as well as read any local media. Keep the repository outside the media working directory; use a local disk for the library. Safari 15.4+ is required for the built-in dialogs.

1. Open ordinary PowerShell in this repository and prepare the local environment:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap-windows.ps1
   ```

   Bootstrap creates `.venv`, installs the pinned runtime requirements, and creates `.env` if it is missing. It does not download or install Python itself, and it preserves an existing `.env`.

2. Edit `.env`:

   ```dotenv
   POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY=D:\MediaProjects
   POCKET_MEDIA_CLIP_SELECTOR_HOST=0.0.0.0
   POCKET_MEDIA_CLIP_SELECTOR_PORT=8767
   ```

   The directory must already exist. Backslashes are literal; don't double them. Paths with spaces or Unicode work, with optional matching quotes. `.env` accepts UTF-8 with an optional BOM. Values are literal: `$`, `%`, and backslashes are preserved without expansion; duplicate assignments are rejected. Real environment variables override `.env`. `POCKET_MEDIA_CLIP_SELECTOR_HOST=0.0.0.0` listens on the PC's IPv4 interfaces. `127.0.0.1` is useful for PC-only checks, but your phone cannot reach that address.

3. Organize the library like this:

   ```text
   D:\MediaProjects\
     A Show - Season 1\
       [Some Group] Episode One.mp4
       totally-arbitrary-name.mp4
       Source\                         # ignored
         original.mkv
       .clipselector\                  # created with the first source
         manifest.json                 # optional; owned by your processor
         project.json                  # owned by this app
     An Example Movie\
       movie.mp4
   ```

   Every immediate child directory is a project, including empty projects. Only MP4 files directly inside a project are playable (`.MP4` also works). Loose files, other formats, and all nested media are ignored. Projects and media sort by case-insensitive filename, then exact filename. Named sources are independent of filenames, and no media manifest is required. Existing folders open immediately and can accept sources without setup. Links, junctions, and other Windows reparse points in the configured path or library are refused.

4. Start in the foreground:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1
   # Optional Python-code reload while developing:
   powershell -ExecutionPolicy Bypass -File .\scripts\run-dev.ps1 -Reload
   ```

   Startup reports the configured listen address. Open `http://127.0.0.1:8767` on the PC. On your iPhone, connect to the same Wi-Fi and open `http://<PC IPv4 address>:8767` in Safari. Find the IPv4 address for your active Wi-Fi/Ethernet adapter with `ipconfig`. Use your configured port if you changed it. Stop a foreground server with Ctrl+C.

5. In Safari, use **Share → Add to Home Screen**. Enable **Open as Web App** if that option appears. Tap **Exit Editor** in Safari and close that tab, then launch **Clip Selector** from its Home Screen icon. If it says the editor is open elsewhere, tap **Take Control**. Turn off Portrait Orientation Lock and rotate the phone to landscape when watching local MP4s. The player is designed around the iPhone 15 Pro's landscape viewport, with space for the notch and home indicator. Project browsing and Quick Log work in portrait.

   The app includes a standalone manifest, an Apple touch icon, and [Apple's Home Screen app metadata](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html) to open without Safari's address bar. If a previously added shortcut still opens in Safari, remove the shortcut and add it again after updating. Home Screen use still requires the PC and Wi-Fi connection; saves are confirmed by the PC.

## Start automatically at your logon

Stop any foreground instance first, then run from ordinary PowerShell in this repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-startup-task.ps1
```

For first-time phone access or after changing the port, run from **PowerShell as Administrator using the same Windows account**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-startup-task.ps1 -ConfigureFirewall
```

This installs and immediately starts **Pocket Media Clip Selector**. The task runs as the current user with limited privileges at that user's logon, through `.venv\Scripts\pythonw.exe`, without a visible console. It uses `IgnoreNew`, has no runtime limit, continues on battery power, and retries errors up to three times at one-minute intervals. When installed from an elevated window, it still registers the task at limited privilege for that same account; don't use a different administrator account.

The optional firewall rule allows the configured TCP port only from `LocalSubnet` on the **Private** profile. Normal installation leaves firewall rules untouched. Keep the Windows network marked Private and use the PC's LAN address on the phone.

One running server reserves the configured library, even when a second copy uses another port. The operating system releases this guard when the process exits or crashes. Use one server/worker and stop the scheduled task before foreground development.

After updating application code, rerun bootstrap to apply any dependency changes, then double-click **`restart-server.cmd`** in the repository root. It stops **Pocket Media Clip Selector**, waits for it to stop, starts it, and verifies a fresh `/health` response from this app. It requests UAC elevation only if Windows denies task-management permission. Success, cancellation, and failures stay visible until you press Enter. Finish active saves first. Reinstall the task after changing startup scripts or moving the repository.

To remove automatic startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\remove-startup-task.ps1
# Optional, from elevated PowerShell: also remove this app's firewall rule.
powershell -ExecutionPolicy Bypass -File .\scripts\remove-startup-task.ps1 -RemoveFirewall
```

Removal stops and unregisters the task. It leaves media, project metadata, and bookmarks in place. Changing the port requires reinstalling the firewall rule with `-ConfigureFirewall`. Changes to `.env` take effect after a server restart. Reload mode watches Python code; refresh Safari after changing frontend assets.

## Bookmark workflow

1. **Projects:** enter a name to create its folder. Existing folders open directly. Project cards and the Sources header show source and bookmark counts; there is no media category or workflow status to maintain.
2. **Sources:** add Episode 01, Episode 02, etc., or use any custom name. Episode naming is the default for every project. Manage lets you rename a source, link/relink/unlink its MP4, or confirm removing the source and its bookmarks. Removing a source never deletes its MP4.
3. **Quick Log:** choose a project/source, type a time, and tap Save Bookmark or submit from the keyboard. The last chosen project/source is remembered on this phone, and a new page opens Quick Log for it. Save confirmation comes from the PC; the field then clears and the same source stays selected. Next Episode creates or opens the following numbered source in one tap. A custom source advances to the next suggested episode.
4. **Bookmarks:** each source lists moments in time order. Edit or delete them even without media. Lists use simple whole-second labels; the local player retains fractional precision internally. An unchanged edit retains that precision. Nearby or identical times are kept as separate intentional bookmarks when saved as separate actions.
5. **Watch:** link a top-level MP4 from Manage, or choose Watch beside a Local MP4 and select an existing source/create one. Rotate to landscape. Bookmark samples the current playback time immediately and saves one timestamp without pausing. Tap a saved bookmark to seek to that moment and continue watching; it never stops automatically. A manual bookmark beyond a linked video's duration remains saved; playback shows the end and asks you to check the association.

Quick Log and Watch & Bookmark share the same records. There are no IN/OUT pairs, capture windows, trimming, or range replay. Finish editing/exporting outside the working folder, then manually delete the completed project folder when ready. The app has no project deletion, permanent archive, TorBox/VLC integration, downloading, transcoding, export, or Premiere automation.

### Entering times

Use the numeric keyboard without typing colons. Digits are interpreted from the right: seconds, then minutes, then hours. Colons work on paste too.

| Input | Saved/displayed time |
| --- | --- |
| `5`, `32` | `0:05`, `0:32` |
| `105`, `332`, `1742` | `1:05`, `3:32`, `17:42` |
| `6000` | `1:00:00` (60 elapsed minutes) |
| `11432`, `123456` | `1:14:32`, `12:34:56` |
| `17:42`, `1:14:32` | Same times |
| `1768`, `1:75:32`, `abc`, `-4`, blank | Rejected; input stays visible |

Seconds must be 00–59. With up to four digits, the minute portion means elapsed minutes and may exceed 59. Five or more digits, or three colon components, require the minute component to be 00–59. Two colon components allow elapsed minutes. Inputs are limited to 16 characters and times through `999:59:59`; numeric API values may retain fractions through `999:59:59.999`. The parser never silently fixes invalid components. It is independent of MP4 duration.

Source names are trimmed and limited to 100 characters. Case and repeated whitespace do not distinguish duplicates. Plain episode labels also treat `Episode 7`, `Episode 07`, `EP 7`, `ep07`, and `Episode 007` as equivalent. A duplicate message names the existing source and offers to open it. Custom labels such as `OVA 1` and `Season 2 - Episode 1` remain distinct.

The landscape player retains scrubbing, Play/Pause, ±5-second seeking, and 1× beside +5 s. The right column offers 0.25×/0.5× and 2×/3×, Bookmark, Quick Log, previous/next playable sources, and Bookmarks. Accepted rates show no routine audio warning. If a rate is rejected, the app reports the actual accepted rate. Safari may limit effective speed or audio at extreme rates; check real iPhone behavior. Short viewports can scroll without hiding controls.

## Project metadata and API

A project gets `.clipselector\project.json` when its first source is saved. Until then, its folder is already usable and has zero sources/bookmarks. The metadata contains only a format version and named sources:

```json
{
  "version": 2,
  "sources": {
    "Episode 07": {
      "media_file": null,
      "bookmarks": [
        { "id": "bkm_example_identity_123", "time": 1062 }
      ]
    }
  }
}
```

Source names are the identities and JSON keys. A rename atomically replaces the key while keeping the association and bookmarks. `media_file` is an exact filename or null, separate from source identity. Bookmark IDs protect explicit retries from duplicate writes. A missing or renamed MP4 never erases/relabels its source or bookmarks. The app does not detect replacement content under the same filename.

The independent processor's `.clipselector\manifest.json`, `Source\` files, and prepared MP4s are untouched. Metadata uses schema version 2. A damaged or unsupported `project.json`, duplicate JSON key, or invalid stored bookmark is reported and never overwritten. Other projects remain browseable.

Source and bookmark mutations save on the PC using a serialized fresh read, temporary-file write, flush/fsync, revision recheck, and atomic replacement. Revisions are SHA-256 hashes of the stored bytes, using the hash of empty bytes when no metadata file exists yet. Back up `project.json` with the project. An interrupted write may leave a harmless `.project-*.tmp` file; remove it only after stopping the server. Project creation only creates a folder. If saving its first source fails, the folder stays usable; explicitly retry that source save.

All library/mutation API calls require `X-Page-Id` and `X-Controller-Token`. The same-origin interface uses these routes:

| Route | Behavior |
| --- | --- |
| `GET /api/projects` | Project names and source/bookmark/media counts |
| `POST /api/projects` | Create a safe folder from `{name}` |
| `GET /api/project?project=…` | Sources, ordered bookmarks, available top-level MP4s, revision |
| `POST /api/sources` | Create a named source with optional `media_file` |
| `PATCH /api/source?project=…&source=…` | Rename and/or change association; omitted fields are preserved |
| `DELETE /api/source` | Remove that source and its bookmarks |
| `POST /api/bookmarks?project=…&source=…` | Add `{id,time}`; identical ID/data retries are idempotent |
| `PATCH /api/bookmarks/{id}` | Edit `{time}` |
| `DELETE /api/bookmarks/{id}` | Delete a bookmark |
| `GET /api/media-info` | Read a prepared MP4's duration |
| `GET/HEAD /media?project=…&file=…` | Direct MP4 byte streaming, independent of ownership |

Project-specific routes use the exact project query parameter; source/bookmark routes also use the exact source name. Source changes and bookmark edit/delete require `If-Match` with the last revision. Add-bookmark requests append to a fresh snapshot without a duration lookup; replaying the same ID with different data is rejected. Nothing is queued offline.

## Editor ownership and uncertain saves

One page controls browsing and editing until it explicitly exits, another page takes control, or the server restarts. The first page automatically claims an unoccupied editor. Other pages show **Take Control**; only an explicit tap transfers ownership. **Exit Editor** releases and pauses playback after the PC confirms it. **Enter Editor** resumes this page's view, draft, and loaded playback position.

Page identities and tokens remain in memory. Browser local storage contains only the last project/source names. Reloading or duplicating a page creates a new identity, so it may require Take Control even when the old page has disappeared. A vanished owner is recovered explicitly. There is no heartbeat, expiry, auto-takeover, background polling, or network monitoring. Safari itself may suspend playback or terminate a page; app lifecycle events do not send ownership requests or force a pause.

API authorization and durable writes share the controller lock. Takeover waits for an authorized write to finish, then rejects every stale token. The old page learns of a transfer on its next ordinary request and offers Take Control while keeping the entry/frame. Explicit takeover refreshes project data; it does not resubmit a save. Corrupt data, stale revisions, or storage errors never produce a success message.

A lost connection may hide a write that actually completed. Quick Log keeps the text and original ID so an **explicit** retry of the unchanged entry is safe. Refresh Bookmarks to confirm what reached the PC. Watch keeps an unconfirmed timestamp and offers Retry/Dismiss; Retry saves that original moment with its original ID while playback continues. Neither workflow automatically retries or claims success early. Drafts and unconfirmed entries stay in this live page's memory; they are not preserved across a full reload or page termination.

## Logs and troubleshooting

Logs, including startup failures, go to `logs\server.log` beside the code. The file rotates at 5 MiB with three backups.

| Symptom | Check |
| --- | --- |
| PC URL fails | `.env`, Python/bootstrap, server log, task state, duplicate server/library lock |
| PC works; iPhone cannot connect | Same LAN, PC awake, active adapter IPv4, Private network/firewall, guest Wi-Fi isolation |
| Open elsewhere after reload | Explicitly Take Control; the previous page identity does not expire |
| Save fails | Free disk space, folder creation/metadata permissions, valid `project.json`, server log |
| Source has a missing MP4 | Manage → choose its current exact top-level filename; bookmarks stay with the source |
| MP4 won't play or seek | Prepared H.264/compatible audio, stable local file, LAN throughput; Quick Log still works |
| Bookmark is past video duration | Verify the association or inspect the end; the saved time is retained |

## Automated verification

Install development dependencies, including Black 25.1.0, then check formatting and run the suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m black --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers name-only project creation, immediately usable existing folders, content counts, source naming and duplicates, atomic rename/association changes, bookmark persistence without media, ordering/edit/delete, idempotent/concurrent adds, damaged JSON, atomic/fsync failures, revision conflicts, exact paths, symlinks, controller transfer/write ordering, process locks, MP4 duration, and HTTP byte ranges/HEAD/If-Range. The Windows junction check runs on Windows.

Frontend checks run under Node.js when available or the development Mac's JavaScriptCore. They cover the timestamp table and invalid/boundary inputs, remembered names without saved tokens, Quick Log validation/Done submission/double-save guards/failed-save retention, idempotent retry, preserving newly typed input during a save, fractional local bookmarks, seek without auto-stop, speed acceptance/rejection, explicit Exit/Enter/takeover, stale responses, and lifecycle events with no polling. The app requires no Node.js or build tools.

Portable PowerShell tests exercise the real scripts with disposable OS adapters. They skip automatically if PowerShell is unavailable; `POCKET_TEST_POWERSHELL` can point to an installed executable. These checks do not register real tasks or change firewall rules. Actual Windows logon, console-free startup, UAC, firewall behavior, and physical iPhone playback still need the checks below.

## Real Windows / iPhone checklist

- [ ] Bootstrap/run foreground and scheduled startup on the intended Windows account, with spaces/Unicode in the library path. Confirm that account can create a project folder and atomically update its metadata. Check current-user/limited logon task, one-server locking, logs, restart on failure, and Private/LocalSubnet firewall scope. Run the Windows junction test.
- [ ] Launch from the iPhone Home Screen without an address bar. Create a media-free project and source in portrait. Verify source/bookmark counts and Episode defaults, including a project folder created outside the app.
- [ ] Watch in VLC, switch to Quick Log, type `1742`, and save using the numeric keyboard's Done action/button. Confirm no colons are needed, invalid seconds stay visible, focus remains convenient, Next Episode takes one tap, and project/source changes are easy with the keyboard open.
- [ ] Exit/reopen or reload the app, explicitly Take Control if prompted, and verify the last chosen project/source and confirmed bookmarks. Remember that unsaved live drafts do not survive page termination.
- [ ] Interrupt Wi-Fi during a save. Confirm the entry remains, no success is claimed, no automatic retry occurs, and retrying an unchanged entry creates only one bookmark. Test unwritable metadata and disk-space failure; compare the existing JSON and media.
- [ ] Later add prepared MP4s, associate/reassociate, and rename sources. Confirm bookmarks stay attached. Remove an accidental source with confirmation and verify its MP4 remains.
- [ ] Watch in both landscape orientations, checking notch/home indicator, long names, touch reach, timeline accuracy, previous/next, and 0.25×/0.5×/1×/2×/3× audio/effective speed. Bookmark while playing and inspect its fractional moment. Tap a saved time and continue watching beyond it. Rotate back to portrait Quick Log.
- [ ] Open another page/device, explicitly transfer ownership, and try a stale write. Confirm rejection, preserved draft/frame, no auto-takeover/polling, and working Exit/Enter. Background/switch apps/lock the phone; distinguish Safari's own suspension/termination from app behavior.
- [ ] Reload/restart the PC server and verify confirmed metadata persists. Finish/export outside the working project folder, then manually delete the completed folder and verify it disappears on Refresh.

The current module responsibilities and operating guarantees are described in [docs/design.md](docs/design.md).
