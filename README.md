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

5. In Safari, use **Share → Add to Home Screen**. Enable **Open as Web App** if that option appears. Tap **Exit Editor** in Safari and close that tab, then launch **Clip Selector** from its Home Screen icon. If it says the editor is open elsewhere, tap **Take Control**. Turn off Portrait Orientation Lock and rotate the phone to landscape when editing. The player is designed around the iPhone 15 Pro's landscape viewport, with space for the notch and home indicator. Project browsing still works in portrait.

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

Removal stops and unregisters the task. It leaves media, project metadata, and saved selections in place. Changing the port requires reinstalling the firewall rule with `-ConfigureFirewall`. Changes to `.env` take effect after a server restart. Reload mode watches Python code; refresh Safari after changing frontend assets.

## Watching and saving

- **Browse:** choose a project and then a video. The Videos/All projects buttons take you back. Previous/Next follow the sorted file order. Refresh discovers files added since the last scan.
- **Editor control:** the first page acquires editing automatically. If another page owns it, tap **Take Control** to transfer ownership explicitly. **Exit Editor** releases ownership and pauses playback after the PC confirms the release. **Enter Editor** resumes the same page with its current video, position, and unfinished marks.
- **Watch:** use landscape for editing. A taller inline video and wide scrubber occupy the left column. Play/Pause, −5 s, +5 s, and 1× sit above the scrubber, followed by the current time and duration. Other speeds, capture, and range controls occupy the compact right column. The previous/next arrows and Selections button sit at its bottom, leaving the video free of a permanent footer. Native video controls remain available. Times retain fractional precision. Shorter viewports can scroll to keep controls reachable.
- **Speed:** tap 1× beside +5 s to return to normal speed. In landscape, the right column has 0.25× and 0.5× on the first row, then 2× and 3× below (these four buttons sit below the scrubber in portrait). The selected button reflects the accepted `video.playbackRate`, with a message if assignment fails or is ignored. Accepted speeds show no routine audio warning and keep the video area clear. A rate changed through native controls is also reflected; an additional actual-rate label appears beside the playback buttons if it doesn't match a preset. Safari can still limit effective playback speed or mute audio at extreme rates even when that property accepts them. Real iPhone behavior, especially 3×, is **not yet verified**.
- **Capture Moment:** samples the current playback time immediately and saves `[time − 15, time + 15]`, clamped to the MP4's duration. It does not pause video. Each capture remains separate, even if ranges overlap. The button is briefly disabled until the PC confirms the write.
- **Manual range:** tap Mark IN and Mark OUT, then Save Range. IN must be earlier than OUT. Reset discards unfinished marks. Successful saves clear the submitted marks.
- **Selections:** all project selections are grouped by exact filename, then start time. Tap a selection to open and replay that range; it pauses at OUT. Play continues beyond it, and seeking exits range replay. Safari may require a second Play tap when opening another video. Adjust accepts decimal seconds and offers ±0.5 second nudges. Delete asks for confirmation.

An unrecognized or renamed filename appears as unavailable and can still be deleted. The app does not retarget selections to another name, including a case-only rename. File identity is the exact relative filename; replacing a video with different content under that same name is not detected. Finish preparing a video before selecting it, and keep it stable afterward.

## Persistence and editor ownership

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

One page owns editing until it explicitly exits, another page takes control, or the server restarts. The first page automatically claims an unoccupied editor. Another page sees **“Clip Selector is open elsewhere”** with **Take Control**. Only tapping that button forces a transfer; blocked pages never acquire automatically or poll for ownership. Page identities and opaque controller tokens stay in memory. Reloading or duplicating a page creates a new identity, so a reload may require Take Control even if the old page has disappeared.

The controller has no heartbeat, expiration, reconnect polling, or network monitoring. Hiding Safari, switching apps, locking the phone, going offline, or navigating away sends no ownership requests and causes no application-enforced pause or disconnect. Safari itself may suspend playback or terminate the page. A vanished owner is recovered through Take Control. **Editor active** describes the page's acquired authority, not a continuously checked PC connection. Nothing is queued for offline saving.

Every library API and selection mutation validates the page identity and token. Streaming and static assets stay independent of ownership. Transfers, releases, and authorized mutations share one server lock held through persistence: a transfer waits for an already authorized write to finish, then invalidates its old token. A waiting stale request is checked after the transfer and rejected before it can write. Serialized storage, atomic replacement, revision checks, and range validation still apply.

The previous page learns about a transfer on its next ordinary API operation. A rejected save displays **“Editor control was transferred to another page”**, disables editing, and offers Take Control while retaining the player, timestamp, and unfinished marks. Playback controls remain usable. Explicit takeover refreshes project/selection data and preserves the loaded video when it is still available. Server restarts clear ownership; an old page must explicitly acquire again.

If a connection fails while saving, the app cannot know whether the PC finished that write. It shows an error and retains the player, playback, and unfinished marks. It does **not** claim success, retry the mutation, or reclaim control automatically. Restore connectivity and refresh selections before saving again. Only a confirmed response produces a success message. An unconfirmed Exit Editor likewise leaves the interface open and reports the failure; retry that action explicitly or take control from another page.

## Logs and troubleshooting

Logs live in `logs\` beside the code, outside `WORKING_DIR`. `server.log` rotates at 5 MiB with three backups. Scheduled startup also creates a timestamped `startup-*.log` that captures startup failures and console output; you can remove old startup logs while the server is stopped.

| Symptom | Check |
| --- | --- |
| PC URL does not open | `.env`, Python/bootstrap, startup logs, task status, and whether another server owns the library or port. |
| PC works; phone cannot connect | Same LAN, PC awake, correct IPv4/port, Private network profile, firewall rule, no guest-network client isolation. |
| Open elsewhere after closing or reloading a tab | Tap Take Control. Ownership lasts until explicit exit, takeover, or server restart. |
| Editor control was transferred | Another page took control. Tap Take Control to edit here again; the current player is preserved. |
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

The tests cover scanner boundaries and sorting, arbitrary Unicode filenames, byte ranges/HEAD/If-Range/invalid ranges, MP4 duration headers, quick-capture clamping, manual ranges, persistent edits/deletes across app restart, stale revisions, duplicate captures, concurrent mutations, automatic first claim, explicit takeover/release, stale-token rejection, ownership without expiration, transfer/write ordering, ownership reset after restart, traversal, symlinks, source/manifest preservation, failed atomic writes, invalid JSON, and duplicate-process locking. A Windows-only junction test runs on Windows. Symlink checks may need Windows Developer Mode or elevation to create their fixtures.

The suite also checks capture/playback, speed-button selection/rejection, five-second seeking, manual exit/reentry, explicit takeover buttons, lifecycle events that leave ownership/playback intact, and uncertain saves that keep the player and marks, using Node.js if available or the system JavaScriptCore executable on the development Mac. It checks that only request deadlines and toast dismissal use timers. This uses a fake DOM and transport; it does not verify browser layout or video decoding. Without either engine, that optional test skips. **Node.js is not needed to run this app.**

Implementation verification on the development Mac used Python 3.13 and the pinned runtime dependencies: **40 tests passed; one Windows junction test was skipped**. The frontend behavior checks ran with JavaScriptCore. A separate live Uvicorn smoke check passed foreground launch, HTTP interface delivery, controller claim, persistent capture, middle-byte streaming, and duplicate-server rejection on a different port; its temporary server was stopped afterward. Windows scripts, Windows mutex/junction behavior, video decoding, and real iPhone speeds/lifecycle remain unverified on their target devices.

The compact two-column landscape layout was checked in Playwright WebKit at 852 × 393, 852 × 340, 667 × 375, 393 × 852, and 1280 × 900, with simulated iPhone safe-area insets and media playback. Both notch orientations and a conservative 59 px inset on each side were checked. At 852 × 393, a 16:9 poster's displayed image height increased from the original stacked layout's 130 px to 236 px (about 3.3 times the image area), with a 554 px timeline and a 172 px editing column. Normal editing, episode-length time labels, and range replay fit without scrolling; smaller viewports and multiple errors can scroll without overlapping navigation. All five accepted playback speeds retain the same video height, including 2×/3× without an audio warning. Speed and range-action buttons are 36 px tall; capture and marks are at least 40 px. Previous/next buttons are 32 × 36 px, while Selections retains its 100 × 44 px area. Direct speed taps and selected-button styling, touch seeking, five-second skips, capture during playback, manual saves and validation, previous/next navigation, selections with a four-digit badge, adjustment dialogs, and rotation passed against a temporary live server. These checks verify layout and UI behavior using a poster and simulated media; actual iPhone decoding, touch accuracy, and Home Screen launch still need the device checks below.

Manual ownership was also checked with two WebKit pages against a temporary live server. Idle pages made no API requests for eighteen seconds, beyond the old expiration period. Simulated visibility/page/network events, an offline save, explicit takeover in both directions, stale-save rejection, confirmed persistence, Exit/Enter Editor, ownership-independent byte streaming, and recovery after closing an owner without releasing all passed. Video playback and safe areas were simulated; the temporary server was stopped afterward.

## Real Windows / iPhone acceptance checklist

These checks remain required on the actual devices. Record the Windows version, Python version, iPhone model, iOS version, and results, particularly for speeds.

- [ ] Bootstrap with the real Windows path, including spaces/Unicode; run the foreground dev and normal scripts. Confirm the printed URL works on PC and iPhone and that logs stay beside the code.
- [ ] Add to Home Screen, close the Safari tab, and launch from the icon. Confirm the app opens without an address bar. Browse projects in portrait, then edit in landscape. Check both landscape orientations, notch/home-indicator clearance, button reach, long filenames, dialogs with the keyboard open, and rotation back to portrait.
- [ ] Play inline. Confirm the actual video image is comfortably large for inspecting movement, its aspect ratio is preserved, and the editing controls fit without scrolling in the Home Screen landscape viewport. Scrub near the start, into the middle of a long episode, and near the end; repeatedly use −5 s and +5 s above the scrubber. Confirm seek responsiveness and current-time/duration display. Use the side-column previous/next arrows and Selections button.
- [ ] Tap **0.25×, 0.5×, 2×, and 3×** in the right column, then **1×** beside +5 s. Record actual observed speed and audio behavior. Confirm the accepted speed is selected and an unsupported rate displays an honest notice/accepted value. Effective 3× playback and audio are unverified until this passes.
- [ ] While video plays, capture near 0 seconds, in the middle, and near the end. Confirm playback continues, the success message follows the write, and ranges clamp correctly. Overlapping captures must remain separate.
- [ ] Mark fractional IN/OUT, save a longer range, try reversed/equal marks, and reset unfinished marks. Replay a saved range, adjust with decimal values/nudges, cancel deletion, then confirm deletion.
- [ ] Close/reopen Safari, reload, and restart the server. Confirm confirmed selections persist. Rename a video and confirm its selections remain unavailable rather than moving to another file.
- [ ] Open a second tab/device: it must show the occupied screen without taking control automatically. Tap Take Control, then attempt capture/adjust/delete from the old page. Confirm rejection, the transfer message, preserved player/marks, and the option to explicitly take control again. Close an owning page without Exit Editor and recover from another page through Take Control.
- [ ] Background the owner for several minutes, switch apps, and lock/unlock the iPhone. Confirm ownership persists and the app does not impose a pause or reconnect screen. Repeat with Wi-Fi loss/recovery and back/forward cache navigation; distinguish Safari's own playback suspension or page termination from app behavior.
- [ ] Tap Exit Editor. Confirm release, then Enter Editor and verify the same video, timestamp, and marks remain. Release again and verify another page can acquire normally. Restart the server and verify a new page can acquire while the old token is rejected.
- [ ] During a save, interrupt connectivity; verify no false success, automatic retry, player reset, or application-enforced pause. Restore connectivity and refresh selections to see whether the write completed. Test a save with a temporarily unwritable metadata folder; retain and compare the existing JSON.
- [ ] Install startup from the intended user's account; confirm no console window, immediate launch, current-user/limited task identity, Private/LocalSubnet firewall scope, and startup after sign-out/sign-in. Confirm the app fails closed when started again while the task runs.
- [ ] End the scheduled server unexpectedly and verify Task Scheduler restarts it after about one minute. Stop/remove the task and confirm the port closes while media and selections stay intact. Run the Windows-only junction test.

## Implementation notes

The referenced repositories were inspected locally **before implementation**:

- [Pocket Manga Editor](https://github.com/ddeka-projects/pocket-manga-editor): `companion/lease.py` informed the initial exclusive active-page model. This app now uses manual ownership with explicit takeover and release. Its production startup runs as SYSTEM; this app instead uses the requested user-logon approach.
- [Pocket Entertainment Catalog](https://github.com/ddeka-projects/pocket-entertainment-catalog): `storage.py`, the user-logon task, and console-free Python runner informed temporary-file/fsync/atomic replacement and Task Scheduler scripts. Its timed/form-only lease and Git synchronization are not used here.
- [Pocket Media Manager](https://github.com/ddeka-projects/pocket-media-manager): the PC helper's FastAPI configuration, media route, and foreground runner informed the small Python server. This app uses `video/mp4`, explicit tested byte ranges, and strict nonrecursive paths.

Code is split into the filesystem library, MP4 header reader, selection store, manual controller ownership, streaming response, API, and small static interface. Streaming uses bounded 256 KiB reads and closes its file on completion/disconnect. It supports single `bytes` ranges including suffix/open-ended forms, returning 206; invalid single byte ranges return 416. Unsupported range units/multipart requests are ignored with a full 200 response, as permitted by HTTP. HEAD returns full headers with no body. If-Range honors matching ETag/Last-Modified values. See [FastAPI response documentation](https://fastapi.tiangolo.com/advanced/custom-response/) and [Uvicorn settings](https://www.uvicorn.org/settings/) for the underlying server behavior.

This remains a personal tool for a trusted home LAN. Future phases can add extraction/export or Premiere integration separately; none is included in v1.0.
