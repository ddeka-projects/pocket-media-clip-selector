import { formatTime, clampSeek, acceptedRate } from "/assets/player.js";

const $ = (id) => document.getElementById(id);
const video = $("video");
// A fresh identity for every JS page load. No sessionStorage/localStorage:
// duplicated Safari tabs must never inherit controller authority.
function newId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes); // Available even on a plain HTTP LAN origin.
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}
const state = { page: newId(), token: null, owned: false, epoch: 0, claimBusy: false, reconnectQueued: false, heartbeatBusy: false,
  project: null, files: [], file: null, view: "library", selections: [], revision: null,
  in: null, out: null, ready: false, saving: false, dragging: false, stopAt: null, pendingSeek: null,
  editing: null, deleting: null, dialogBusy: false, heartbeat: null, retry: null, toast: null };

function url(path, extra = {}) {
  const query = new URLSearchParams({ ...(state.project ? { project: state.project } : {}), ...extra });
  const encoded = query.toString();
  return path + (encoded ? `?${encoded}` : "");
}

class ApiError extends Error {
  constructor(message, code = "network_error") { super(message); this.code = code; }
}

async function request(path, { method = "GET", body, revision, controller = true } = {}) {
  if (controller && !state.owned) throw new ApiError("Reconnect before saving.", "lease_expired");
  const epoch = state.epoch;
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 12000);
  try {
    const headers = { Accept: "application/json" };
    if (body) headers["Content-Type"] = "application/json";
    if (controller) { headers["X-Page-Id"] = state.page; headers["X-Lease-Token"] = state.token; }
    if (revision) headers["If-Match"] = revision;
    const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined,
      cache: "no-store", credentials: "same-origin", signal: abort.signal });
    const payload = await response.json();
    if (epoch !== state.epoch) throw new ApiError("The page session changed. Refresh your selections.", "session_changed");
    if (!response.ok) throw new ApiError(payload.error?.message || "The PC could not complete this request.", payload.error?.code || "request_failed");
    return payload;
  } catch (error) {
    if (epoch !== state.epoch) throw new ApiError("The page session changed. Refresh your selections.", "session_changed");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Cannot confirm the request. Check the connection, then refresh selections before trying a save again.");
  } finally { clearTimeout(timeout); }
}

function toast(message, error = false) {
  clearTimeout(state.toast);
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").hidden = false;
  state.toast = setTimeout(() => { $("toast").hidden = true; }, error ? 8000 : 2600);
}

function disconnect(title, detail, retry = true) {
  state.owned = false;
  state.epoch += 1;
  state.heartbeatBusy = false;
  clearInterval(state.heartbeat);
  clearTimeout(state.retry);
  video.pause();
  for (const id of ["edit-dialog", "delete-dialog"]) if ($(id).open) $(id).close();
  $("workspace").hidden = true;
  $("gate").hidden = false;
  $("gate-title").textContent = title;
  $("gate-detail").textContent = detail;
  $("retry").hidden = !retry;
  $("connection").textContent = "Disconnected";
  $("connection").classList.remove("live");
  document.body.classList.remove("player-open");
  updateControls();
}

function handleError(error) {
  if (["session_changed"].includes(error.code)) return;
  if (error.code === "lease_conflict") {
    disconnect("Clip Selector is open elsewhere", "Another tab or device is using the app. Close that page, or wait 15 seconds after it stops responding, then retry.");
    state.retry = setTimeout(connect, 5000);
  } else if (error.code === "lease_expired" || error.code === "network_error") {
    disconnect("Reconnect to your PC", error.message);
    state.retry = setTimeout(connect, 5000);
  } else toast(error.message, true);
}

async function connect() {
  if (document.hidden) return;
  if (state.claimBusy) { state.reconnectQueued = true; return; }
  state.claimBusy = true;
  clearTimeout(state.retry);
  const epoch = state.epoch;
  try {
    const result = await request("/api/controller/claim", { method: "POST", body: { page_id: state.page }, controller: false });
    if (document.hidden || epoch !== state.epoch) return;
    state.token = result.token;
    state.owned = true;
    $("connection").textContent = "PC connected";
    $("connection").classList.add("live");
    clearInterval(state.heartbeat);
    state.heartbeat = setInterval(heartbeat, 5000);
    if (state.project) {
      try {
        const project = await request(url("/api/project"));
        state.files = project.media;
        await loadSelections();
        if (state.file && !state.files.some((file) => file.name === state.file)) {
          state.file = null;
          state.view = "library";
          video.removeAttribute("src"); video.load();
          toast("The previous video is unavailable.", true);
        }
      } catch (error) {
        if (error.code !== "unavailable") throw error;
        state.project = null; state.file = null; state.view = "library";
      }
    }
    $("gate").hidden = true;
    $("workspace").hidden = false;
    if (state.view === "library") await loadLibrary();
    else if (state.view === "selections") renderSelections();
    showView(state.view);
    updateControls();
  } catch (error) {
    if (state.owned && !["lease_conflict", "lease_expired", "network_error", "session_changed"].includes(error.code)) {
      $("gate").hidden = true; $("workspace").hidden = false; showView(state.view); updateControls();
    }
    handleError(error);
  } finally {
    state.claimBusy = false;
    if (state.reconnectQueued) { state.reconnectQueued = false; state.retry = setTimeout(connect, 0); }
  }
}

async function heartbeat() {
  if (!state.owned || document.hidden || state.heartbeatBusy) return;
  state.heartbeatBusy = true;
  try { await request("/api/controller/heartbeat", { method: "POST", body: { page_id: state.page, token: state.token }, controller: false }); }
  catch (error) { handleError(error); }
  finally { state.heartbeatBusy = false; }
}

function showView(view) {
  state.view = view;
  document.body.classList.toggle("player-open", view === "player");
  if (view !== "player") video.pause();
  for (const name of ["library", "player", "selections"]) $(`${name}-view`).hidden = name !== view;
  $("media-navigation").hidden = view !== "player";
  $("tabs").hidden = !state.project;
  $("player-tab").disabled = !state.file;
  $("player-tab").setAttribute("aria-current", view === "player" ? "page" : "false");
  $("selections-tab").setAttribute("aria-current", view === "selections" ? "page" : "false");
  $("back").hidden = !state.project;
  $("back").textContent = view === "library" ? "‹ All projects" : "‹ Videos";
  $("project-context").textContent = state.project || "ON YOUR PC";
}

function makeButton(text, className, action) {
  const button = document.createElement("button");
  button.type = "button"; button.className = className; button.textContent = text;
  button.addEventListener("click", action);
  return button;
}

function empty(container, message) {
  const element = document.createElement("p"); element.className = "empty"; element.textContent = message;
  container.append(element);
}

async function loadLibrary() {
  const chosen = state.project;
  const result = await request(chosen ? url("/api/project") : "/api/projects");
  if (chosen !== state.project) return;
  if (chosen) state.files = result.media;
  $("library-title").textContent = chosen || "Your projects";
  $("library-kicker").textContent = chosen ? "CHOOSE A VIDEO" : "FIND YOUR NEXT SCENE";
  $("library-detail").textContent = chosen ? "Watch, find a moment, and capture it." : "Choose a project to start watching.";
  const list = $("library-list"); list.replaceChildren();
  const items = chosen ? result.media : result.projects;
  for (const item of items) {
    const card = makeButton("", "library-card", () => {
      if (chosen) openMedia(item.name);
      else void openProject(item.name).catch(handleError);
    });
    const text = document.createElement("span"); text.className = "card-text";
    const title = document.createElement("span"); title.className = "card-title"; title.textContent = item.name;
    const meta = document.createElement("span"); meta.className = "card-meta";
    meta.textContent = chosen ? `${(item.bytes / 1024 / 1024).toFixed(0)} MB · MP4` : `${item.media_count} ${item.media_count === 1 ? "video" : "videos"}`;
    const arrow = document.createElement("span"); arrow.className = "card-arrow"; arrow.textContent = "›"; arrow.setAttribute("aria-hidden", "true");
    text.append(title, meta); card.append(text, arrow); list.append(card);
  }
  if (!items.length) empty(list, chosen ? "No top-level MP4 videos in this project yet. Put prepared MP4 files directly in its folder, then refresh." : "No projects yet. Add a project folder inside your media working directory, then refresh.");
}

async function openProject(name) {
  state.project = name; state.file = null; state.in = state.out = null;
  video.removeAttribute("src"); video.load();
  showView("library");
  await loadLibrary(); await loadSelections();
}

function openMedia(file, selection = null) {
  if (!state.owned) return;
  const changed = state.file !== file;
  state.file = file; state.in = state.out = null;
  state.stopAt = selection ? selection.end : null;
  $("replay-note").hidden = !selection;
  $("replay-note").textContent = selection ? `Replaying ${formatTime(selection.start)} – ${formatTime(selection.end)}` : "";
  $("media-title").textContent = file;
  const index = state.files.findIndex((entry) => entry.name === file);
  $("media-index").textContent = `Video ${index + 1} of ${state.files.length}`;
  $("previous").disabled = index <= 0;
  $("next").disabled = index < 0 || index >= state.files.length - 1;
  $("video-error").hidden = true;
  showView("player");
  if (changed || !video.getAttribute("src")) {
    state.ready = false;
    state.pendingSeek = selection ? selection.start : 0;
    video.src = url("/media", { file }); video.load();
    $("current-time").textContent = "0:00.000"; $("duration").textContent = "—";
  } else if (selection) video.currentTime = clampSeek(selection.start, video.duration);
  updateControls();
  // Selection replay starts from the user's tap. New videos wait for Play.
  if (selection) void video.play().catch(() => toast("Tap Play to replay the selection."));
  window.scrollTo({ top: 0 });
}

function updateControls() {
  const ready = state.owned && state.ready;
  for (const id of ["play", "scrubber", "mark-in", "mark-out"]) $(id).disabled = !ready;
  for (const button of document.querySelectorAll("[data-skip], [data-rate]")) button.disabled = !ready;
  $("capture").disabled = !ready || state.saving;
  $("save-range").disabled = !ready || state.saving || state.in === null || state.out === null || state.in >= state.out;
  $("reset-range").disabled = state.in === null && state.out === null;
  $("in-value").textContent = formatTime(state.in);
  $("out-value").textContent = formatTime(state.out);
  $("range-detail").textContent = state.in !== null && state.out !== null && state.in >= state.out ? "IN must be earlier than OUT. Mark either point again." : "Mark the beginning and end while watching.";
}

function updateTime() {
  $("current-time").textContent = formatTime(video.currentTime);
  if (!state.dragging) $("scrubber").value = String(video.currentTime);
  if (state.stopAt !== null && video.currentTime >= state.stopAt) {
    video.pause(); video.currentTime = state.stopAt; state.stopAt = null;
    $("replay-note").textContent = "Selection finished. Press Play to continue watching.";
  }
}

function seek(time) {
  if (!state.ready || !state.owned) return;
  state.stopAt = null; $("replay-note").hidden = true;
  video.currentTime = clampSeek(time, video.duration); updateTime();
}

function installSelections(result) {
  state.selections = result.selections; state.revision = result.revision;
  $("selection-count").textContent = String(result.selections.length);
}

async function loadSelections() {
  const project = state.project;
  const result = await request(url("/api/selections"));
  if (project === state.project) installSelections(result);
}

async function save(kind) {
  if (state.saving || !state.ready || !state.owned) return;
  const file = state.file, project = state.project, identity = newId();
  const moment = video.currentTime; // Sample immediately, before any network work.
  const bounds = { start: state.in, end: state.out };
  if (kind === "range" && (bounds.start === null || bounds.end === null || bounds.start >= bounds.end)) return;
  state.saving = true; updateControls();
  try {
    const body = kind === "capture" ? { id: identity, file, time: moment } : { id: identity, file, ...bounds };
    const result = await request(url(kind === "capture" ? "/api/selections/capture" : "/api/selections", { project }), { method: "POST", body });
    if (project === state.project) installSelections(result);
    const saved = result.selections.find((row) => row.id === identity);
    toast(`Saved ${formatTime(saved.start)} – ${formatTime(saved.end)}`);
    if (kind === "range" && file === state.file && project === state.project && state.in === bounds.start && state.out === bounds.end) state.in = state.out = null;
  } catch (error) { handleError(error); }
  finally { state.saving = false; updateControls(); }
}

function renderSelections() {
  const list = $("selections-list"); list.replaceChildren();
  let group = null, lastFile = null;
  for (const selection of state.selections) {
    if (lastFile !== selection.file) {
      group = document.createElement("div"); group.className = "selection-group";
      const heading = document.createElement("h2"); heading.textContent = selection.file;
      group.append(heading); list.append(group); lastFile = selection.file;
    }
    const card = document.createElement("div"); card.className = "selection-card";
    const replay = makeButton(`${selection.available ? "▶ " : ""}${formatTime(selection.start)} – ${formatTime(selection.end)}`, "selection-replay", () => openMedia(selection.file, selection));
    replay.disabled = !selection.available;
    const length = document.createElement("p"); length.className = "selection-length"; length.textContent = `${(selection.end - selection.start).toFixed(3)} seconds`;
    card.append(replay, length);
    if (!selection.available) {
      const note = document.createElement("p"); note.className = "unavailable-note"; note.textContent = "Unavailable · the exact source filename is missing or was renamed."; card.append(note);
    }
    const actions = document.createElement("div"); actions.className = "selection-actions";
    const edit = makeButton("Adjust", "", () => editSelection(selection)); edit.disabled = !selection.available;
    const remove = makeButton("Delete", "delete-button", () => deleteSelection(selection));
    actions.append(edit, remove); card.append(actions); group.append(card);
  }
  $("selections-detail").textContent = `${state.selections.length} saved ${state.selections.length === 1 ? "selection" : "selections"} on your PC. Tap a range to replay it.`;
  if (!state.selections.length) empty(list, "Your moments will appear here. Open a video and tap Capture Moment, or mark an IN/OUT range.");
}

function editSelection(selection) {
  state.editing = { ...selection, revision: state.revision, project: state.project };
  $("edit-file").textContent = selection.file;
  $("edit-start").value = String(selection.start); $("edit-end").value = String(selection.end);
  $("edit-error").hidden = true; updateEditPreview(); $("edit-dialog").showModal();
}

function updateEditPreview() {
  const start = $("edit-start").valueAsNumber, end = $("edit-end").valueAsNumber;
  $("edit-preview").textContent = `${formatTime(start)} – ${formatTime(end)}`;
  $("edit-save").disabled = state.dialogBusy || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || start >= end;
}

function deleteSelection(selection) {
  state.deleting = { ...selection, revision: state.revision, project: state.project };
  $("delete-detail").textContent = `${selection.file} · ${formatTime(selection.start)} – ${formatTime(selection.end)}`;
  $("delete-error").hidden = true; $("delete-dialog").showModal();
}

async function changeSelection(event, kind) {
  event.preventDefault();
  if (state.dialogBusy || !state.owned) return;
  const row = kind === "edit" ? state.editing : state.deleting;
  state.dialogBusy = true;
  for (const button of document.querySelectorAll(`#${kind}-dialog button`)) button.disabled = true;
  try {
    const body = kind === "edit" ? { start: $("edit-start").valueAsNumber, end: $("edit-end").valueAsNumber } : undefined;
    const result = await request(url(`/api/selections/${row.id}`, { project: row.project }), { method: kind === "edit" ? "PATCH" : "DELETE", body, revision: row.revision });
    installSelections(result); renderSelections(); $(`${kind}-dialog`).close(); toast(kind === "edit" ? "Changes saved on your PC." : "Selection deleted.");
  } catch (error) {
    $(`${kind}-error`).textContent = error.message; $(`${kind}-error`).hidden = false;
    if (error.code === "selection_conflict") {
      $(`${kind}-dialog`).close();
      try { await loadSelections(); renderSelections(); } catch (reloadError) { handleError(reloadError); }
    }
    handleError(error);
  } finally {
    state.dialogBusy = false;
    for (const button of document.querySelectorAll(`#${kind}-dialog button`)) button.disabled = false;
    updateEditPreview();
  }
}

$("retry").addEventListener("click", connect);
$("refresh").addEventListener("click", () => void loadLibrary().catch(handleError));
$("back").addEventListener("click", () => {
  if (state.view === "library") { state.project = null; state.file = null; video.removeAttribute("src"); video.load(); }
  showView("library"); void loadLibrary().catch(handleError);
});
$("player-tab").addEventListener("click", () => showView("player"));
async function showSelections() { showView("selections"); try { await loadSelections(); renderSelections(); } catch (error) { handleError(error); } }
$("selections-tab").addEventListener("click", showSelections);
$("refresh-selections").addEventListener("click", showSelections);
$("play").addEventListener("click", () => { if (video.paused) void video.play().catch(() => toast("Safari could not play this video. Check the MP4 and connection.", true)); else video.pause(); });
for (const name of ["play", "pause", "ended"]) video.addEventListener(name, () => { $("play").textContent = video.paused ? "Play" : "Pause"; });
video.addEventListener("loadedmetadata", () => {
  state.ready = Number.isFinite(video.duration) && video.duration > 0;
  $("duration").textContent = formatTime(video.duration); $("scrubber").max = String(video.duration);
  if (state.pendingSeek !== null && state.ready) { video.currentTime = clampSeek(state.pendingSeek, video.duration); state.pendingSeek = null; }
  syncRate(); updateControls(); updateTime();
});
video.addEventListener("emptied", () => { state.ready = false; updateControls(); });
video.addEventListener("timeupdate", updateTime);
video.addEventListener("error", () => { state.ready = false; updateControls(); $("video-error").textContent = "Cannot play this MP4. Check that the PC is reachable and this is a prepared H.264 MP4 with compatible audio."; $("video-error").hidden = false; });
for (const button of document.querySelectorAll("[data-skip]")) button.addEventListener("click", () => seek(video.currentTime + Number(button.dataset.skip)));
$("scrubber").addEventListener("pointerdown", () => { state.dragging = true; });
$("scrubber").addEventListener("input", () => seek(Number($("scrubber").value)));
for (const event of ["change", "pointerup", "pointercancel"]) $("scrubber").addEventListener(event, () => { state.dragging = false; updateTime(); });

function syncRate() {
  const actual = video.playbackRate;
  let matched = false;
  for (const button of document.querySelectorAll("[data-rate]")) {
    const selected = Math.abs(Number(button.dataset.rate) - actual) < 0.001;
    button.setAttribute("aria-pressed", String(selected));
    matched ||= selected;
  }
  $("actual-speed").hidden = matched;
  $("actual-speed").textContent = `${actual}× actual`;
}
video.addEventListener("ratechange", syncRate);
for (const button of document.querySelectorAll("[data-rate]")) button.addEventListener("click", () => {
  if (!state.owned || !state.ready) return;
  const requested = Number(button.dataset.rate), result = acceptedRate(video, requested);
  syncRate(); $("speed-notice").hidden = result.accepted;
  $("speed-notice").textContent = `Safari did not accept ${requested}×. Playing at ${result.rate}×.`;
  if (result.accepted && requested >= 2) { $("speed-notice").hidden = false; $("speed-notice").textContent = "Audio or effective speed may be limited by Safari at this rate."; }
});
$("capture").addEventListener("click", () => void save("capture"));
$("mark-in").addEventListener("click", () => { state.in = video.currentTime; updateControls(); });
$("mark-out").addEventListener("click", () => { state.out = video.currentTime; updateControls(); });
$("save-range").addEventListener("click", () => void save("range"));
$("reset-range").addEventListener("click", () => { state.in = state.out = null; updateControls(); });
for (const [id, offset] of [["previous", -1], ["next", 1]]) $(id).addEventListener("click", () => { const index = state.files.findIndex((file) => file.name === state.file); if (state.files[index + offset]) openMedia(state.files[index + offset].name); });
for (const input of ["edit-start", "edit-end"]) $(input).addEventListener("input", updateEditPreview);
for (const button of document.querySelectorAll("[data-nudge]")) button.addEventListener("click", () => { const [field, delta] = button.dataset.nudge.split(":"); const input = $(`edit-${field}`); input.value = String(Math.max(0, Math.round((input.valueAsNumber + Number(delta)) * 1000) / 1000)); updateEditPreview(); });
$("edit-form").addEventListener("submit", (event) => void changeSelection(event, "edit"));
$("delete-form").addEventListener("submit", (event) => void changeSelection(event, "delete"));
for (const kind of ["edit", "delete"]) {
  $(`${kind}-cancel`).addEventListener("click", () => $(`${kind}-dialog`).close());
  $(`${kind}-dialog`).addEventListener("cancel", (event) => { if (state.dialogBusy) event.preventDefault(); });
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) { disconnect("Reconnecting", "Checking controller ownership when you return…", false); }
  else void connect();
});
window.addEventListener("pagehide", () => {
  const token = state.token;
  if (token) void fetch("/api/controller/release", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page_id: state.page, token }), keepalive: true }).catch(() => {});
  disconnect("Reconnecting", "Reopening your local library…", false);
});
window.addEventListener("pageshow", (event) => { if (event.persisted) void connect(); });
window.addEventListener("online", () => { if (!state.owned) void connect(); });
window.addEventListener("offline", () => disconnect("Your phone is offline", "Reconnect to the same local network as your PC, then try again."));
void connect();
