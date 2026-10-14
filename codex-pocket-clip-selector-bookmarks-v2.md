# Pocket Media Clip Selector — Bookmark-First Workflow Redesign

**Codex implementation brief | October 2026**  
**Repository:** https://github.com/ddeka-projects/pocket-media-clip-selector  
**Target:** Implement the new workflow end to end in the existing repository, not a proposal or a separate application.  
**Platform:** Windows PC server; iPhone Safari / Add to Home Screen client.

## 1. Goal and guiding principle

Refactor the existing Clip Selector into a **project-based media bookmark tool**. The user often discovers interesting scenes while streaming anime MKVs from TorBox in **VLC on iPhone**. Those videos will **not** be playable in the Clip Selector and need not exist on the PC. The user simply types a rough timestamp into the web app and saves a **bookmark** against a named source (usually an episode). Much later, the user may download and convert the footage, inspect bookmarks in the existing local MP4 player, and perform all precise clipping/trimming in **Adobe Premiere Pro**.

There are exactly **two bookmark-capture methods**:

1. **Quick Log (manual):** enter a time observed in VLC or another player. Requires no local media file.
2. **Watch & Bookmark (local):** play an already-prepared MP4 in the existing mobile player, and press **Bookmark** to save its current time.

Both feed the **same project > named source > bookmarks** data model. One bookmark represents **one time**, not a range. Do not keep IN/OUT editing, +/-15-second capture, start/end pairs, range replay, or range adjustment anywhere in the new UI or new storage model. Removing them is an intentional product decision, not an accidental loss of features.

Prioritize ease of use over speculative infrastructure. Do not integrate TorBox, VLC, FFmpeg, live transcoding, download automation, Premiere project generation, exporting, or Apple Shortcuts in this iteration.

## 2. Existing implementation: preserve what still helps

Inspect the current repository before editing. It currently contains a working Python/FastAPI/Uvicorn local server, a vanilla HTML/CSS/JS iPhone interface, correct MP4 HTTP byte-range streaming, a landscape-oriented local player with seeking and playback-speed controls, PWA/Home Screen support, manual **Take Control / Exit Editor** ownership, safe file-path handling, atomic JSON persistence, tests, and Windows PowerShell startup / Task Scheduler scripts.

**Retain and adapt** those working parts. In particular:

- Preserve the polished local-video playback experience and useful transport controls, including 0.25x/0.5x/1x/2x/3x speeds, +/-5s seeking, scrubbing, previous/next, and the compact landscape layout.
- Preserve the local LAN-only, no-account, no-cloud design and Windows user-logon startup.
- Preserve the existing explicit editor ownership model: first page claims; other pages may explicitly **Take Control**; **Exit Editor** releases; do not reintroduce heartbeat expiry, auto-takeover, or background polling.
- Preserve server-side authorization, atomic writes, revision/conflict checks, path traversal and Windows junction/symlink protections, and process locking.
- Keep the source footage and the separate media processor's `.clipselector/manifest.json` untouched.

**Breaking change expressly permitted:** The user has no old selections that need preserving. Do **not** implement backwards-compatible reading or migration of the existing `.clipselector/selections.json` schema. The old range endpoints, storage models, views, tests, and README text can be replaced outright. Do not spend time supporting both formats. Do not, however, delete unrelated media or processor files.

## 3. Project model and life cycle

The configured `WORKING_DIR` retains the current convention: each immediate subfolder is one editing project. The repository code lives outside the work directory. A project can exist and contain bookmarks **without any downloaded media**.

**Required project workflow:**

1. From iPhone, browse existing project folders or create a new project folder safely.
2. On creation, choose exactly one project category from this list:
   - Anime
   - Donghua
   - Other Animation
   - Live Action Movies
   - Live Action Series
   - Video Game
3. Add one or more named sources and log bookmarks, even when there are no MP4s.
4. Later, associate downloaded/converted MP4s with their existing named sources; keep all bookmarks.
5. After editing and exporting outside the working project folder, the user manually deletes the completed project folder. **Do not automate deletion or maintain a separate permanent archive.**

For a simple work-in-progress overview, give each project a small editable status: **Discovering** (default) or **Editing**. Show category, status, source count and bookmark count in project browsing. No task management, deadlines, completion percentages, or automatic Premiere detection.

Existing folders created outside the app must remain browseable. If an existing project has no new-format project metadata, allow the user to choose a category and initialize it without modifying its existing media files. Do not require a media manifest.

## 4. Named sources (episode-first, independent of filenames)

Inside each project, the basic unit is a **source**. A source is what the user thinks of as `Episode 07`, `OVA 1`, `Part 2`, `Movie`, or any other custom name. It does **not** require a local MP4.

- **Use the source's user-visible name as its identity within the project.** Do not introduce invisible UUID identifiers for sources merely for hypothetical future features.
- Default source naming for **all six categories**, including movies and video games: **Episode 01**, **Episode 02**, etc. Suggest the next available episode number; users can override the entire name freely.
- Source names must be nonempty after trimming, reasonably bounded, safe to serialize, and unique within the project. Preserve the user's selected display spelling.
- Support **rename**; changing the name must preserve all bookmarks and any linked local MP4. Make the rename an atomic metadata update.
- Provide a way to remove an accidentally created source, with a confirmation that its bookmarks will be removed. Do not delete an associated MP4.

### Minimal duplicate-name protection

Handle this **server-side** on both create and rename:

1. Compare ordinary names after trimming, collapsing repeated whitespace, and case-insensitive normalization. E.g., `Episode 07`, `episode 07`, and ` Episode   07 ` must not coexist.
2. For plain numeric episode labels, additionally recognize `Episode 7`, `Episode 07`, `EP 7`, `ep07`, and `Episode 007` as the **same logical episode number**. Leading zeros, capitalization, and the common `Ep` abbreviation do not make distinct sources. Provide a useful conflict message pointing to the existing source (e.g., `Episode 07 already exists`) and a way to open it.
3. Do **not** build general fuzzy matching, IMDb matching, semantic similarity, or a full taxonomy. Names such as `OVA 1` and `Season 2 - Episode 1` are valid custom names and are not automatically equivalent to `Episode 01`.

Use a small, readable normalization helper with dedicated tests; avoid elaborate duplicate detection.

## 5. Bookmarks only

A bookmark belongs to **one named source** and stores a **single, nonnegative timestamp in seconds**. No `start`, `end`, or +/-15-second values.

- Manual bookmarks are ordinarily whole seconds.
- The local player can capture `video.currentTime` with its fractional precision internally, but the ordinary bookmark list should show simple readable times such as `3:32`, `17:42`, or `1:14:32`.
- List bookmarks under their source in ascending time order. Allow a bookmark's time to be edited or the bookmark to be deleted. A short optional note may be allowed if it adds no friction, but it must never be required.
- Do not automatically merge two nearby bookmarks or interpret them as a range; two nearby timestamps may be intentional.
- On an associated local MP4, tapping a bookmark should seek the player to the marked moment, allowing the user to inspect the surrounding footage. No range-replay or auto-stop behavior.
- A manual bookmark must save even if no local MP4 exists and no duration can be inspected. Validate timestamp format and numeric value, not an imaginary file duration.
- Never claim a save succeeded before the PC confirms it. Retain the entry on a failed or uncertain save, with the existing safe failure handling.

Individual bookmark records may use a small internal unique `id` to make edit/delete requests safe; **the decision to use name-based identity applies to sources, not necessarily to individual bookmark mutation IDs.**

## 6. Quick Log: minimize every unnecessary tap

This is the highest-priority new user experience. The usual situation: the user is watching a TorBox MKV in VLC, notices a scene at `17:42`, briefly opens the iPhone web app, and wants to record it with almost no interruption.

**Ideal flow:** Open Quick Log -> existing project/source already selected -> type `1742` -> tap **Save Bookmark** or keyboard **Done** -> brief confirmation -> clear input, ready for the next bookmark. No start/end inputs, modal confirmation, or forced notes.

- Remember the last-used project and source across page launches on the same phone (e.g., browser local storage). Do **not** persist editor-controller tokens or share them between tabs.
- Make it easy to change project/source and advance to **Next Episode** without navigating through multiple screens. When creating a new source, default to the next suggested `Episode XX`.
- Use an iPhone-friendly numeric keyboard via a **text** input with appropriate `inputmode` (do not use an HTML number input that loses leading zeroes or makes pasted colon formats inconvenient).
- Focus/select the time field when the user explicitly opens Quick Log where iOS permits; after a successful save, clear it and keep the same source selected.
- Accept Save via button or keyboard submission; prevent double taps from creating accidental duplicate writes. Show compact feedback, not a disruptive dialog.
- Keep Quick Log comfortable in **portrait** as well as landscape. Do not damage the local player's landscape layout.

### Timestamp parser: exact behavior

Parse digit-only input **from right to left**: last two digits = seconds, preceding two digits = minutes, remaining leading digits = hours. One to three digits are valid and implicitly left-padded. Also accept colon-separated `MM:SS` and `H:MM:SS` on paste/entry. Normalize valid times for display and store numeric seconds.

| Entered | Display / meaning | Result |
|---|---|---|
| `5` | `0:05` | Accept |
| `32` | `0:32` | Accept |
| `105` | `1:05` | Accept |
| `332` | `3:32` | Accept |
| `1742` | `17:42` | Accept |
| `6000` | `1:00:00` (60 elapsed minutes) | Accept |
| `11432` | `1:14:32` | Accept |
| `123456` | `12:34:56` | Accept |
| `17:42` | `17:42` | Accept |
| `1:14:32` | `1:14:32` | Accept |
| `1768` | Invalid seconds (`68`) | **Reject** |
| `1:75:32` | Invalid minute component (`75`) | **Reject** |
| `abc`, `-4`, empty input | Invalid | **Reject** |

**Explicit validation rule:** Never silently correct invalid seconds or an invalid `H:MM:SS` minute component. For digit-only input of **up to four digits**, the minute portion represents *total elapsed minutes*, so `6000` is valid and normalizes to one hour; the final two seconds must still be `00` through `59`. For digit-only input with **five or more digits**, the two minute digits must be `00` through `59`. Colon-form `MM:SS` can likewise represent elapsed minutes, but `H:MM:SS` must have minute and second components under 60. Allow only sensible, bounded nonnegative values with no numeric overflow. Leave invalid input visible and explain why it cannot be saved.

Prefer a small pure parser/formatter helper with comprehensive tests. The server still validates any numeric seconds submitted by the client (finite, >= 0). The user should never have to type colons for ordinary timestamps.

## 7. Local MP4 integration, without tying identity to filenames

Continue scanning only regular **top-level `.mp4` files** under each project, ignoring `Source/`, `.clipselector/`, and nested folders, as the current code does.

- Each named source optionally has an associated exact top-level MP4 filename (`media_file` or equivalent). That is a **playback association**, not the source's identity.
- A source with no MP4 still appears in the source list and supports manual bookmarks.
- Provide a straightforward UI to **associate/reassociate** an existing source with one of the project's prepared MP4 files. An incorrect/missing association should not erase bookmarks or relabel the source.
- Keep a simple path for somebody who already has MP4s in a project: browse an available local MP4, select an existing named source or create one quickly, and then use **Watch & Bookmark**. Avoid tedious mandatory setup just to play a prepared file.
- Preserve filename safety checks and exact matching for **physical media paths**; that is separate from the user's source naming.
- Keep transport/speed/seek and mobile landscape ergonomics. Replace `Capture Moment` with a single **Bookmark** button that samples `video.currentTime` at the instant of the tap. Remove the manual range controls and their associated CSS/JS.

## 8. Metadata and persistence

Use a single simple project-local metadata representation; one suggested new location is `<WORKING_DIR>/<PROJECT>/.clipselector/project.json`. It must coexist with the independent media processor's `.clipselector/manifest.json` and `Source/` directory. Choose a clear schema, document it, and implement it consistently.

**Illustrative new-format JSON (free to refine):**

```json
{
  "version": 1,
  "category": "Anime",
  "status": "Discovering",
  "sources": {
    "Episode 07": {
      "media_file": null,
      "bookmarks": [
        { "id": "bkm_abc123", "time": 1062 },
        { "id": "bkm_def456", "time": 1145 }
      ]
    }
  }
}
```

Source names are **keys** in this example; renames replace the key and retain its contents. Source names are unique within a project, not globally. Bookmark IDs are optional implementation details if a similarly safe small mutation strategy is chosen. Save on the Windows PC after every confirmed create/edit/delete. Reuse atomic temporary-file write + flush/fsync + replace, revision-conflict handling, and authorized single-controller mutations. Protect against damaged new-format JSON rather than silently overwriting it.

No database, Git synchronization, cloud sync, durable external archive, or old-format migration. Since this is still development, the old range-oriented selection metadata may be ignored/discarded by the user; **do not build compatibility code**.

## 9. UI information architecture

Keep navigation lean. A workable structure is:

**Projects** (category / status / counts; create project) -> **Sources** (Episode 01, Episode 02, etc.; add/rename/remove; show bookmark counts and MP4 availability) -> **Quick Log**, **Bookmarks**, and **Watch** (only if linked MP4 exists).

Do not add complicated source-type-specific screens. All six categories use the same default Episode naming and same bookmark behavior. Treat Quick Log as a first-class action, not an obscure form hidden behind the player. Keep existing Home Screen/PWA behavior and takeover UX intact. Prefer a consistent style with the current application rather than a wholesale visual redesign.

## 10. Explicitly out of scope

- TorBox or VLC integration, externally pasted stream playback, remote codecs, proxies, HLS or transcoding.
- Apple Shortcuts / Action Button integration (future idea only).
- Downloading media, editing/converting media, FFmpeg changes, or integration with the existing separate conversion script.
- Premiere Pro project creation, automatic clip extraction/trimming, exported videos, or automated project-folder deletion.
- Reintroducing time ranges as a secondary or legacy feature.
- Fuzzy source-name matching, third-party metadata lookups, or elaborate project management.
- Supporting / migrating the old selections JSON schema.

## 11. Tests and acceptance criteria

Update the existing backend and frontend tests rather than retaining tests for removed range features. Cover at minimum:

1. Creating a project from the phone/API, category validation, default status, initialization of an existing folder, and project/status/count listing.
2. Creating/editing/deleting a named source; generating sequential Episode labels; supporting custom labels for all six categories.
3. Rejecting duplicates on **creation and rename**, including case/whitespace variants and `Episode 7` versus `Episode 07` versus `ep07`; custom names not accidentally merged.
4. Correct timestamp parser results for the table above, plus boundary/large-number/invalid cases; invalid input must not be saved or auto-corrected.
5. Adding, sorting, editing, deleting, and persisting single-time bookmarks **with no local MP4**; bookmarks survive browser/server restart.
6. Associating/reassociating top-level MP4s with named sources; bookmarks stay attached through source rename and file-association changes; unsafe paths are rejected.
7. Local player saves a timestamp, not a range; bookmark navigation seeks to the saved moment; existing speed, transport and range-streaming behavior still work.
8. Atomic write failure, damaged metadata, stale revision, repeated requests, concurrent edits, control takeover/release, and prevention of stale-controller writes.
9. Quick Log retains the selected source, keeps keyboard entry low-friction, submits on Done/button, prevents accidental double saves, and does not discard unsaved input on connection failure.
10. Windows scripts still launch the app with correct local-library permissions, and the iPhone landscape player and portrait Quick Log are usable.

Run the available automated tests; report precisely what ran. Include a focused real Windows/iPhone manual checklist for anything that cannot be verified in the development environment. Remove/update outdated README statements about ranges, Capture Moment, old JSON, and legacy APIs.

## 12. Execution instruction to Codex

**Implement this bookmark-first redesign end to end in `ddeka-projects/pocket-media-clip-selector`.** First inspect the present code/tests and reuse the existing stable building blocks; then update the data model, API, frontend, persistence, README, and automated tests together. Do not stop at a design document or scaffold. Make minor implementation decisions independently in favor of a small, reliable, attractive iPhone workflow. It is acceptable—and expected—to remove obsolete range-oriented code entirely and break old selection-metadata compatibility. Preserve the LAN-only security posture, current Windows deployment behavior, prepared-MP4 playback quality, and manual controller-ownership semantics. Finish with a concise summary of implemented behavior, test results, and remaining real-device checks.
