# Pocket Media Clip Selector

Bookmark-first v2 keeps moments from any player in **project → named source → bookmarks**. While watching in VLC, open Quick Log, type a time such as `1742`, and save `17:42` on your Windows PC. No local media is required. Later, link a prepared MP4 to the same source and inspect those moments in the landscape player. Precise editing stays in Premiere Pro.

The app uses Python, FastAPI, Uvicorn, and vanilla HTML/CSS/JavaScript. It has no frontend build step, database, accounts, cloud service, media conversion, or final clip export. The PC must stay awake and the server must be running.

## Windows setup

You need Windows PowerShell 5.1+, Python 3.10+ from [python.org](https://www.python.org/downloads/windows/). For local playback, use prepared H.264 MP4 videos with Safari-compatible audio. Use an ordinary Windows account that can create project folders and write their metadata, as well as read any local media. Keep the repository outside the media working directory; use a local disk for the library. Safari 15.4+ is required for the built-in dialogs.

1. Open PowerShell in this repository. If Windows blocks local scripts, allow them for this window:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\bootstrap-windows.ps1
   ```

   Bootstrap creates `.venv`, installs the pinned runtime requirements, and creates `.env` if it is missing. It does not download or install Python itself, and it preserves an existing `.env`.

2. Edit `.env`:

   ```dotenv
   WORKING_DIR=D:\MediaProjects
   HOST=0.0.0.0
   PORT=8767
   ```

   The directory must already exist. Backslashes are literal; don't double them. Paths with spaces or Unicode work, with optional surrounding quotes. Real environment variables override `.env`. `HOST=0.0.0.0` listens on the PC's IPv4 interfaces. `127.0.0.1` is useful for PC-only checks, but your phone cannot reach that address.

3. Organize the library like this:

   ```text
   D:\MediaProjects\
     A Show - Season 1\
       [Some Group] Episode One.mp4
       totally-arbitrary-name.mp4
       Source\                         # ignored
         original.mkv
       .clipselector\                  # created when initialized
         manifest.json                 # optional; owned by your processor
         project.json                  # owned by this app
     An Example Movie\
       movie.mp4
   ```

   Every immediate child directory is a project, including empty projects. Only MP4 files directly inside a project are playable (`.MP4` also works). Loose files, other formats, and all nested media are ignored. Projects and media sort by case-insensitive filename, then exact filename. Named sources are independent of filenames, and no media manifest is required. Existing folders can be initialized by choosing a category in the app. Links, junctions, and other Windows reparse points in the configured path or library are refused.

4. Start in the foreground:

   ```powershell
   .\scripts\run-dev.ps1
   # Optional Python-code reload while developing:
   .\scripts\run-dev.ps1 -Reload
   # Normal foreground operation, no reload:
   .\scripts\run-server.ps1
   ```

   Startup prints the PC and local-network URLs. Open `http://127.0.0.1:8767` on the PC. On your iPhone, connect to the same Wi-Fi and open a printed `http://<PC IPv4 address>:8767` URL in Safari. If several addresses appear, use the IPv4 address for your active Wi-Fi/Ethernet adapter (`ipconfig`). Use your configured port if you changed it. Stop a foreground server with Ctrl+C.

5. In Safari, use **Share → Add to Home Screen**. Enable **Open as Web App** if that option appears. Tap **Exit Editor** in Safari and close that tab, then launch **Clip Selector** from its Home Screen icon. If it says the editor is open elsewhere, tap **Take Control**. Turn off Portrait Orientation Lock and rotate the phone to landscape when watching local MP4s. The player is designed around the iPhone 15 Pro's landscape viewport, with space for the notch and home indicator. Project browsing and Quick Log work in portrait.

   The app includes a standalone manifest, an Apple touch icon, and [Apple's Home Screen app metadata](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html) to open without Safari's address bar. If a previously added shortcut still opens in Safari, remove the shortcut and add it again after updating. Home Screen use still requires the PC and Wi-Fi connection; saves are confirmed by the PC.

## Start automatically at your logon

Stop any foreground instance first. For initial network setup, open **PowerShell as Administrator using the same Windows account**, change to this repository, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-startup-task.ps1 -ConfigureFirewall
```

This installs and immediately starts **Pocket Media Clip Selector**. The task runs as the current user with limited privileges at that user's logon, through `.venv\Scripts\pythonw.exe`, without a visible console. It uses `IgnoreNew`, has no runtime limit, continues on battery power, and retries nonzero exits every minute up to 999 times. It does not run as SYSTEM or before sign-in. When installed from an elevated window, it still registers the task at limited privilege for that same account; don't use a different administrator account.

The firewall option creates one inbound TCP rule for the configured port, **Private profile and LocalSubnet only**. Keep your home network marked Private in Windows settings. The rule also works for foreground startup. If a firewall permission dialog appears later, cancel it instead of adding broader Python rules. Check Windows Firewall for pre-existing broad Python rules if you have used Python servers before. No router forwarding or public internet deployment is needed.

Once the firewall is configured, task installation/updating can be run from ordinary PowerShell:

```powershell
.\scripts\install-startup-task.ps1
Get-ScheduledTaskInfo -TaskName "Pocket Media Clip Selector"
```

The app also takes an OS-owned lock for the configured library and binds one fixed port, so accidental second server processes or extra Uvicorn workers fail to start. Use one process / one worker. Do not start a development server while the scheduled server is running. To temporarily switch to foreground development:

```powershell
Stop-ScheduledTask -TaskName "Pocket Media Clip Selector"
.\scripts\run-dev.ps1
# After stopping development with Ctrl+C:
Start-ScheduledTask -TaskName "Pocket Media Clip Selector"
```

To remove automatic startup:

```powershell
.\scripts\remove-startup-task.ps1
# Optional, from elevated PowerShell: also remove this app's firewall rule.
.\scripts\remove-startup-task.ps1 -RemoveFirewall
```

Removal stops and unregisters the task. It leaves media, project metadata, and bookmarks in place. Changing the port requires reinstalling the firewall rule with `-ConfigureFirewall`. Changes to `.env` take effect after a server restart. Reload mode watches Python code; refresh Safari after changing frontend assets.

## Bookmark workflow

1. **Projects:** create a folder with one category: Anime, Donghua, Other Animation, Live Action Movies, Live Action Series, or Video Game. Existing folders ask for a category once. Each project shows its category, Discovering/Editing status, source count, and bookmark count. Change status from Sources.
2. **Sources:** add Episode 01, Episode 02, etc., or use any custom name. The default naming is the same for all categories. Manage lets you rename a source, link/relink/unlink its MP4, or confirm removing the source and its bookmarks. Removing a source never deletes its MP4.
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

A project has one metadata file, `.clipselector\project.json`:

```json
{
  "version": 1,
  "category": "Anime",
  "status": "Discovering",
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

The independent processor's `.clipselector\manifest.json`, `Source\` files, and prepared MP4s are untouched. Old `.clipselector\selections.json` is ignored and left in place: this is a breaking redesign without migration or legacy endpoints. A damaged/unsupported new `project.json`, duplicate JSON key, or invalid stored bookmark is reported and never overwritten. Other projects remain browseable.

Every mutation saves on the PC using a serialized fresh read, temporary-file write, flush/fsync, revision recheck, and atomic replacement. Revisions are SHA-256 hashes of the stored bytes, including an empty-file hash for uninitialized folders. Back up `project.json` with the project. An interrupted write may leave a harmless `.project-*.tmp` file; remove it only after stopping the server. A failed initial project save can leave an empty folder; refresh Projects and initialize that folder rather than creating another one.

All library/mutation API calls require `X-Page-Id` and `X-Controller-Token`. The same-origin interface uses these routes:

| Route | Behavior |
| --- | --- |
| `GET /api/projects` | Project summaries, categories, statuses |
| `POST /api/projects` | Create a safe folder and category metadata |
| `GET /api/project?project=…` | Sources, ordered bookmarks, available top-level MP4s, revision |
| `POST /api/project/initialize` | Categorize an existing folder |
| `PATCH /api/project` | Change Discovering/Editing status |
| `POST /api/sources` | Create a named source with optional `media_file` |
| `PATCH /api/source?project=…&source=…` | Rename and/or change association; omitted fields are preserved |
| `DELETE /api/source` | Remove that source and its bookmarks |
| `POST /api/bookmarks?project=…&source=…` | Add `{id,time}`; identical ID/data retries are idempotent |
| `PATCH /api/bookmarks/{id}` | Edit `{time}` |
| `DELETE /api/bookmarks/{id}` | Delete a bookmark |
| `GET /api/media-info` | Read a prepared MP4's duration |
| `GET/HEAD /media?project=…&file=…` | Direct MP4 byte streaming, independent of ownership |

Project-specific routes use the exact project query parameter; source/bookmark routes also use the exact source name. Initialization, status, source changes, and bookmark edit/delete require `If-Match` with the last revision. Add-bookmark requests append to a fresh snapshot without a duration lookup; replaying the same ID with different data is rejected. Nothing is queued offline.

## Editor ownership and uncertain saves

One page owns editing until it explicitly exits, another page takes control, or the server restarts. The first page automatically claims an unoccupied editor. Other pages show **Take Control**; only an explicit tap transfers ownership. **Exit Editor** releases and pauses playback after the PC confirms it. **Enter Editor** resumes this page's view, draft, and loaded playback position.

Page identities and tokens remain in memory. Browser local storage contains only the last project/source names. Reloading or duplicating a page creates a new identity, so it may require Take Control even when the old page has disappeared. A vanished owner is recovered explicitly. There is no heartbeat, expiry, auto-takeover, background polling, or network monitoring. Safari itself may suspend playback or terminate a page; app lifecycle events do not send ownership requests or force a pause.

API authorization and durable writes share the controller lock. Takeover waits for an authorized write to finish, then rejects every stale token. The old page learns of a transfer on its next ordinary request and offers Take Control while keeping the entry/frame. Explicit takeover refreshes project data; it does not resubmit a save. Corrupt data, stale revisions, or storage errors never produce a success message.

A lost connection may hide a write that actually completed. Quick Log keeps the text and original ID so an **explicit** retry of the unchanged entry is safe. Refresh Bookmarks to confirm what reached the PC. Watch keeps an unconfirmed timestamp and offers Retry/Dismiss; Retry saves that original moment with its original ID while playback continues. Neither workflow automatically retries or claims success early. Drafts and unconfirmed entries stay in this live page's memory; they are not preserved across a full reload or page termination.

## Logs and troubleshooting

Logs stay in `logs\` beside the code. `server.log` rotates at 5 MiB with three backups. Console-free startup also records `startup-*.log` files.

| Symptom | Check |
| --- | --- |
| PC URL fails | `.env`, Python/bootstrap, startup logs, task state, duplicate server/library lock |
| PC works; iPhone cannot connect | Same LAN, PC awake, active adapter IPv4, Private network/firewall, guest Wi-Fi isolation |
| Open elsewhere after reload | Explicitly Take Control; the previous page identity does not expire |
| Project needs initialization | Choose one of the six categories; media and manifest stay untouched |
| Save fails | Free disk space, folder creation/metadata permissions, valid `project.json`, server log |
| Source has a missing MP4 | Manage → choose its current exact top-level filename; bookmarks stay with the source |
| MP4 won't play or seek | Prepared H.264/compatible audio, stable local file, LAN throughput; Quick Log still works |
| Bookmark is past video duration | Verify the association or inspect the end; the saved time is retained |

## Automated verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers project creation/initialization, categories/status/counts, source naming and duplicates, atomic rename/association changes, bookmark persistence without media, ordering/edit/delete, idempotent/concurrent adds, damaged JSON, atomic/fsync failures, revision conflicts, exact paths, symlinks, controller transfer/write ordering, process locks, MP4 duration, and HTTP byte ranges/HEAD/If-Range. The Windows junction check runs on Windows.

Frontend checks run under Node.js when available or the development Mac's JavaScriptCore. They cover the timestamp table and invalid/boundary inputs, remembered names without saved tokens, Quick Log validation/Done submission/double-save guards/failed-save retention, idempotent retry, preserving newly typed input during a save, fractional local bookmarks, seek without auto-stop, speed acceptance/rejection, explicit Exit/Enter/takeover, stale responses, and lifecycle events with no polling. The app requires no Node.js or build tools.

Development verification used Python 3.13: **44 tests passed, one Windows junction test skipped**. A live Uvicorn/WebKit workflow exercised phone-driven project/source creation, no-media Quick Log, duplicate source handling, rename/remove, bookmark editing, offline failure, a committed write with a lost response and explicit retry, remembered Quick Log after reload, later MP4 linking, Link & Watch, transport/speed/bookmark navigation, explicit controller takeover, and processor-file preservation. Layout checks used 393 × 852 portrait, 852 × 393 landscape with both notch orientations and conservative safe areas, a shorter 852 × 340 viewport, and 1280 × 900 desktop. Normal iPhone-sized landscape editing fits without scrolling. Safe areas and media playback were simulated; physical iPhone decoding, numeric keyboard behavior, and Windows startup still need the checks below.

## Real Windows / iPhone checklist

- [ ] Bootstrap/run foreground and scheduled startup on the intended Windows account, with spaces/Unicode in the library path. Confirm that account can create a project folder and atomically update its metadata. Check current-user/limited logon task, one-server locking, logs, restart on failure, and Private/LocalSubnet firewall scope. Run the Windows junction test.
- [ ] Launch from the iPhone Home Screen without an address bar. Create a media-free project and source in portrait. Verify category/status/counts and all six categories' Episode defaults.
- [ ] Watch in VLC, switch to Quick Log, type `1742`, and save using the numeric keyboard's Done action/button. Confirm no colons are needed, invalid seconds stay visible, focus remains convenient, Next Episode takes one tap, and project/source changes are easy with the keyboard open.
- [ ] Exit/reopen or reload the app, explicitly Take Control if prompted, and verify the last chosen project/source and confirmed bookmarks. Remember that unsaved live drafts do not survive page termination.
- [ ] Interrupt Wi-Fi during a save. Confirm the entry remains, no success is claimed, no automatic retry occurs, and retrying an unchanged entry creates only one bookmark. Test unwritable metadata and disk-space failure; compare the existing JSON and media.
- [ ] Later add prepared MP4s, associate/reassociate, and rename sources. Confirm bookmarks stay attached. Remove an accidental source with confirmation and verify its MP4 remains.
- [ ] Watch in both landscape orientations, checking notch/home indicator, long names, touch reach, timeline accuracy, previous/next, and 0.25×/0.5×/1×/2×/3× audio/effective speed. Bookmark while playing and inspect its fractional moment. Tap a saved time and continue watching beyond it. Rotate back to portrait Quick Log.
- [ ] Open another page/device, explicitly transfer ownership, and try a stale write. Confirm rejection, preserved draft/frame, no auto-takeover/polling, and working Exit/Enter. Background/switch apps/lock the phone; distinguish Safari's own suspension/termination from app behavior.
- [ ] Reload/restart the PC server and verify confirmed metadata persists. Finish/export outside the working project folder, then manually delete the completed folder and verify it disappears on Refresh.

The application remains a personal, LAN-only tool. The Windows deployment scripts and MP4 byte-streaming implementation are retained; the v2 redesign changes the project metadata, API, and bookmark interface.
