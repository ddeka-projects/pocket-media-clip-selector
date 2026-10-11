# Pocket Media Clip Selector

Find scenes on your iPhone and save their timestamps on your Windows PC. MVP 1.0 serves your existing, prepared MP4 files over your home network. Capture a moment while it plays, mark a longer IN/OUT range, and revisit or adjust your selections later.

The app uses Python, FastAPI, Uvicorn, and vanilla HTML/CSS/JavaScript. It has no frontend build step, database, accounts, cloud service, media conversion, or final clip export. The PC must stay awake and the server must be running.

## Windows setup

You need Windows PowerShell 5.1+, Python 3.10+ from [python.org](https://www.python.org/downloads/windows/), and prepared H.264 MP4 videos with Safari-compatible audio. Use an ordinary Windows account that can read the media and write project metadata. Keep the repository outside the media working directory; use a local disk for the library. Safari 15.4+ is required for the built-in selection dialogs.

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
       .clipselector\                  # created on first save
         manifest.json                 # optional; owned by your processor
         selections.json               # owned by this app
     An Example Movie\
       movie.mp4
   ```

   Every immediate child directory is a project, including empty projects. Only MP4 files directly inside a project are playable (`.MP4` also works). Loose files, other formats, and all nested media are ignored. Projects and media sort by case-insensitive filename, then exact filename. There is no episode-name convention and no manifest requirement. Links, junctions, and other Windows reparse points in the configured path or library are refused.

4. Start in the foreground:

   ```powershell
   .\scripts\run-dev.ps1
   # Optional Python-code reload while developing:
   .\scripts\run-dev.ps1 -Reload
   # Normal foreground operation, no reload:
   .\scripts\run-server.ps1
   ```

   Startup prints the PC and local-network URLs. Open `http://127.0.0.1:8767` on the PC. On your iPhone, connect to the same Wi-Fi and open a printed `http://<PC IPv4 address>:8767` URL in Safari. If several addresses appear, use the IPv4 address for your active Wi-Fi/Ethernet adapter (`ipconfig`). Use your configured port if you changed it. Stop a foreground server with Ctrl+C.

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

Removal stops and unregisters the task. It leaves media, project metadata, and saved selections in place. Changing the port requires reinstalling the firewall rule with `-ConfigureFirewall`. Changes to `.env` take effect after a server restart. Reload mode watches Python code; refresh Safari after changing frontend assets.

## Watching and saving

- **Browse:** choose a project and then a video. The Videos/All projects buttons take you back. Previous/Next follow the sorted file order. Refresh discovers files added since the last scan.
- **Watch:** video plays inline in portrait mode. Native controls remain available alongside a touch scrubber, Play/Pause, and −15/−5/+5/+15 second skips. Times retain fractional precision.
- **Speed:** choose 0.25×, 0.5×, 1×, 2×, or 3×. The app reads back `video.playbackRate` and shows the accepted value, with a message if assignment fails or is ignored. Safari can still limit effective playback speed or mute audio at extreme rates even when that property accepts them. Real iPhone behavior, especially 3×, is **not yet verified**.
- **Capture Moment:** samples the current playback time immediately and saves `[time − 15, time + 15]`, clamped to the MP4's duration. It does not pause video. Each capture remains separate, even if ranges overlap. The button is briefly disabled until the PC confirms the write.
- **Manual range:** tap Mark IN and Mark OUT, then Save Range. IN must be earlier than OUT. Reset discards unfinished marks. Successful saves clear the submitted marks.
- **Selections:** all project selections are grouped by exact filename, then start time. Tap a selection to open and replay that range; it pauses at OUT. Play continues beyond it, and seeking exits range replay. Safari may require a second Play tap when opening another video. Adjust accepts decimal seconds and offers ±0.5 second nudges. Delete asks for confirmation.

An unrecognized or renamed filename appears as unavailable and can still be deleted. The app does not retarget selections to another name, including a case-only rename. File identity is the exact relative filename; replacing a video with different content under that same name is not detected. Finish preparing a video before selecting it, and keep it stable afterward.

## Persistence and connection behavior

Each project lazily gets `.clipselector\selections.json` on the first confirmed save:

```json
{
  "version": 1,
  "selections": [
    { "id": "unique-stable-selection-id", "file": "movie.mp4", "start": 502.25, "end": 519.75 }
  ]
}
```

Adds, edits, and deletes write on the PC immediately. The server validates finite ranges against the MP4's movie-header duration, serializes changes, flushes and syncs a temporary file in the same metadata directory, and atomically replaces the JSON. Failed writes retain the old JSON and show an error. Edits/deletes carry a revision to reject stale changes. Stable add IDs protect against an identical request being delivered twice. Browser/server restarts keep selections; unfinished marks and playback position are not persisted.

The application writes only selection metadata and temporary selection files in the media tree. It never modifies MP4s, original downloads, or the processor's manifest. It refuses damaged/unsupported selection JSON instead of replacing it. Back up these small JSON files along with your projects. A crash can leave a harmless `.selections-*.tmp` file; after stopping the server, you may remove that temporary file. Keep `.clipselector\selections.json`.

The first page controls the entire app. A second tab/device sees **“Clip Selector is open elsewhere”** and can retry; it also retries every five seconds. Page identities are newly generated in memory for each load, so duplicating a tab does not share authority. Heartbeats run every five seconds and expire after fifteen seconds. All library APIs and every selection mutation check the live server lease. Streams and static assets are read-only and do not need lease headers.

On Safari suspension or loss of connectivity, the interface disables access and pauses playback. On return it claims/renews ownership and refreshes project/selection data. It stays occupied if another page took control. Page close/navigation tries to release ownership; a missed signal is recovered by expiry. An old token cannot authorize writes after a new claim. Server restarts clear leases. Nothing is queued for offline saving.

If a connection fails while saving, the app cannot know whether the PC finished that write. It does **not** claim success or retry the mutation automatically. Reconnect and refresh selections before capturing again. Only a confirmed response produces a success message.

## Logs and troubleshooting

Logs live in `logs\` beside the code, outside `WORKING_DIR`. `server.log` rotates at 5 MiB with three backups. Scheduled startup also creates a timestamped `startup-*.log` that captures startup failures and console output; you can remove old startup logs while the server is stopped.

| Symptom | Check |
| --- | --- |
| PC URL does not open | `.env`, Python/bootstrap, startup logs, task status, and whether another server owns the library or port. |
| PC works; phone cannot connect | Same LAN, PC awake, correct IPv4/port, Private network profile, firewall rule, no guest-network client isolation. |
| Open elsewhere after closing a tab | Wait fifteen seconds, then retry. Close other tabs/devices still using the app. |
| A video is absent | It must be a regular top-level MP4 in an immediate project directory. Nested files and links are ignored. Refresh. |
| Video will not play or seek | Prepared H.264 MP4, compatible audio, stable source file, LAN throughput, and the real-iPhone checklist below. |
| Save fails | Free disk space, current-user permissions for the project, valid selection JSON, and `server.log`. Never discard an error assuming the save succeeded. |
| Duration cannot be read | Use a normal, non-fragmented prepared MP4 with a finite `moov/mvhd` duration. Conversion is the separate processor's responsibility. |
| Task starts under the wrong account | Reinstall from the intended user's PowerShell; do not use another account for elevation. |

## Automated checks

On Windows, from this repository:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover scanner boundaries and sorting, arbitrary Unicode filenames, byte ranges/HEAD/If-Range/invalid ranges, MP4 duration headers, quick-capture clamping, manual ranges, persistent edits/deletes across app restart, stale revisions, duplicate captures, concurrent mutations, lease expiry/reclaim/release, traversal, symlinks, source/manifest preservation, failed atomic writes, invalid JSON, and duplicate-process locking. A Windows-only junction test runs on Windows. Symlink checks may need Windows Developer Mode or elevation to create their fixtures.

The suite also checks capture/playback and lifecycle JavaScript behavior using Node.js if available, or the system JavaScriptCore executable on the development Mac. This uses a fake DOM and transport; it does not verify browser layout or video decoding. Without either engine, that optional test skips. **Node.js is not needed to run this app.**

Implementation verification on the development Mac used Python 3.13 and the pinned runtime dependencies: **34 tests passed; one Windows junction test was skipped**. The frontend behavior checks ran with JavaScriptCore. A separate live Uvicorn smoke check passed foreground launch, HTTP interface delivery, controller claim, persistent capture, middle-byte streaming, and duplicate-server rejection on a different port; its temporary server was stopped afterward. Windows scripts, Windows mutex/junction behavior, browser layout/decoding, and real iPhone speeds/lifecycle remain unverified on their target devices.

## Real Windows / iPhone acceptance checklist

These checks remain required on the actual devices. Record the Windows version, Python version, iPhone model, iOS version, and results, particularly for speeds.

- [ ] Bootstrap with the real Windows path, including spaces/Unicode; run the foreground dev and normal scripts. Confirm the printed URL works on PC and iPhone and that logs stay beside the code.
- [ ] In portrait Safari, navigate projects/videos/back/previous/next. Check button reach, text wrapping, dialogs with the keyboard open, and orientation changes.
- [ ] Play inline. Scrub near the start, into the middle of a long episode, and near the end; repeatedly use all four skip buttons. Confirm seek responsiveness and current-time/duration display.
- [ ] Try **0.25×, 0.5×, 1×, 2×, and 3×**. Record actual observed speed and audio behavior. Confirm an unsupported rate displays an honest notice/accepted value. Effective 3× playback and audio are unverified until this passes.
- [ ] While video plays, capture near 0 seconds, in the middle, and near the end. Confirm playback continues, the success message follows the write, and ranges clamp correctly. Overlapping captures must remain separate.
- [ ] Mark fractional IN/OUT, save a longer range, try reversed/equal marks, and reset unfinished marks. Replay a saved range, adjust with decimal values/nudges, cancel deletion, then confirm deletion.
- [ ] Close/reopen Safari, reload, and restart the server. Confirm confirmed selections persist. Rename a video and confirm its selections remain unavailable rather than moving to another file.
- [ ] Open a second tab and a second device: they must show the occupied screen. Background the owner for over fifteen seconds, claim from the second page, and return to the owner; it must stay blocked. Repeat with app switching, screen lock, Wi-Fi loss/recovery, and back/forward cache navigation.
- [ ] During a save, interrupt connectivity; verify no false success. Refresh on reconnection to see whether the write completed. Test a save with a temporarily unwritable metadata folder; retain and compare the existing JSON.
- [ ] Install startup from the intended user's account; confirm no console window, immediate launch, current-user/limited task identity, Private/LocalSubnet firewall scope, and startup after sign-out/sign-in. Confirm the app fails closed when started again while the task runs.
- [ ] End the scheduled server unexpectedly and verify Task Scheduler restarts it after about one minute. Stop/remove the task and confirm the port closes while media and selections stay intact. Run the Windows-only junction test.

## Implementation notes

The referenced repositories were inspected locally **before implementation**:

- [Pocket Manga Editor](https://github.com/ddeka-projects/pocket-manga-editor): `companion/lease.py` and the frontend's claim/heartbeat/visibility/pagehide handling informed the exclusive active-page model. Its production startup runs as SYSTEM; this app instead uses the requested user-logon approach.
- [Pocket Entertainment Catalog](https://github.com/ddeka-projects/pocket-entertainment-catalog): `lease.py`, `storage.py`, the user-logon task, and console-free Python runner informed the five/fifteen-second lease, temporary-file/fsync/atomic replacement, and Task Scheduler scripts. Its form-only lease and Git synchronization were not brought over.
- [Pocket Media Manager](https://github.com/ddeka-projects/pocket-media-manager): the PC helper's FastAPI configuration, media route, and foreground runner informed the small Python server. This app uses `video/mp4`, explicit tested byte ranges, and strict nonrecursive paths.

Code is split into the filesystem library, MP4 header reader, selection store, lease, streaming response, API, and small static interface. Streaming uses bounded 256 KiB reads and closes its file on completion/disconnect. It supports single `bytes` ranges including suffix/open-ended forms, returning 206; invalid single byte ranges return 416. Unsupported range units/multipart requests are ignored with a full 200 response, as permitted by HTTP. HEAD returns full headers with no body. If-Range honors matching ETag/Last-Modified values. See [FastAPI response documentation](https://fastapi.tiangolo.com/advanced/custom-response/) and [Uvicorn settings](https://www.uvicorn.org/settings/) for the underlying server behavior.

This remains a personal tool for a trusted home LAN. Future phases can add extraction/export or Premiere integration separately; none is included in v1.0.
