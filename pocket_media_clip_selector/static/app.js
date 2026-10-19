import { formatTime, clampSeek, acceptedRate } from "/assets/player.js";
import { parseTimestamp, formatBookmark, compactTimestamp } from "/assets/bookmarks.js";

const $ = (id) => document.getElementById(id);
const video = $("video");
const dialogs = ["project", "source", "link", "edit", "confirm"];
function newId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes); // Works on a plain HTTP LAN origin.
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}
// Only the chosen names are remembered. Page identities and controller tokens
// remain in memory, so a duplicated tab never inherits editing authority.
const preferenceKey = "pocket-clip-selector:last-source";
function readPreference() {
  try {
    const saved = JSON.parse(localStorage.getItem(preferenceKey));
    if (typeof saved?.project === "string" && typeof saved?.source === "string") return { project: saved.project, source: saved.source };
  } catch { /* Private browsing or disabled local storage must not block use. */ }
  return null;
}
const state = { page: newId(), token: null, owned: false, epoch: 0, controlBusy: false, busy: false,
  projects: [], project: null, meta: null, source: null, view: "projects", loadVersion: 0,
  remembered: readPreference(), drafts: new Map(), watchPending: null, loaded: null,
  ready: false, dragging: false, pendingSeek: null, sourceDialog: null, linking: null,
  editing: null, confirming: null, conflictSource: null, toast: null };

function currentSource() { return state.meta?.sources.find((source) => source.name === state.source) || null; }
function remember() {
  if (!state.project || !state.source) return;
  state.remembered = { project: state.project, source: state.source };
  try { localStorage.setItem(preferenceKey, JSON.stringify(state.remembered)); } catch { /* Optional convenience. */ }
}
function draftFor(project = state.project, source = state.source) {
  const key = JSON.stringify([project, source]);
  if (!state.drafts.has(key)) state.drafts.set(key, { raw: "", version: 0, pending: null });
  return state.drafts.get(key);
}
function url(path, extra = {}) {
  const query = new URLSearchParams({ ...(state.project ? { project: state.project } : {}), ...extra });
  const encoded = query.toString();
  return path + (encoded ? `?${encoded}` : "");
}
class ApiError extends Error {
  constructor(message, code = "network_error", details = {}) { super(message); this.code = code; this.source = details.source; }
}
async function request(path, { method = "GET", body, revision, controller = true } = {}) {
  if (controller && !state.owned) throw new ApiError("Take Control to save here again.", "controller_required");
  const epoch = state.epoch, abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 12000);
  try {
    const headers = { Accept: "application/json" };
    if (body) headers["Content-Type"] = "application/json";
    if (controller) { headers["X-Page-Id"] = state.page; headers["X-Controller-Token"] = state.token; }
    if (revision) headers["If-Match"] = revision;
    const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined,
      cache: "no-store", credentials: "same-origin", signal: abort.signal });
    const payload = await response.json();
    if (epoch !== state.epoch) throw new ApiError("The page session changed. Refresh the project.", "session_changed");
    if (!response.ok) throw new ApiError(payload.error?.message || "The PC could not complete this request.", payload.error?.code || "request_failed", payload.error);
    return payload;
  } catch (error) {
    if (epoch !== state.epoch) throw new ApiError("The page session changed. Refresh the project.", "session_changed");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Cannot confirm the request. Your entry is kept. Check the connection and refresh bookmarks, or explicitly retry the same entry.");
  } finally { clearTimeout(timeout); }
}
function toast(message, error = false) {
  clearTimeout(state.toast); $("toast").textContent = message;
  $("toast").classList.toggle("error", error); $("toast").hidden = false;
  state.toast = setTimeout(() => { $("toast").hidden = true; }, error ? 8000 : 2600);
}
function fieldError(id, error) { $(id).textContent = error.message; $(id).hidden = false; }
function showGate(title, detail, { takeover = false, retry = false } = {}) {
  $("workspace").hidden = true; $("gate").hidden = false;
  $("gate-title").textContent = title; $("gate-detail").textContent = detail;
  $("gate-take-control").hidden = !takeover; $("retry").hidden = !retry;
  document.body.classList.remove("player-open");
}
function loseControl(message) {
  state.owned = false; state.token = null; state.epoch += 1;
  for (const name of dialogs) if ($(`${name}-dialog`).open) $(`${name}-dialog`).close();
  $("connection").textContent = "Control not held"; $("connection").classList.remove("live");
  if ($("workspace").hidden) showGate(message, "Tap Take Control to save on this page.", { takeover: true });
  else { $("control-message").textContent = message; $("control-notice").hidden = false; }
  render();
}
function handleError(error) {
  if (error.code === "session_changed") return;
  if (["controller_occupied", "controller_transferred", "controller_required"].includes(error.code)) loseControl(error.message);
  else toast(error.message, true);
}
async function mutate(action, onError = handleError) {
  if (state.busy || state.controlBusy || !state.owned) return;
  state.busy = true; updateControls();
  try { await action(); }
  catch (error) { onError(error); }
  finally { state.busy = false; updateControls(); }
}
function installProject(snapshot) {
  if (snapshot.name !== state.project) return false;
  state.loadVersion += 1; state.meta = snapshot;
  const index = state.projects.findIndex((project) => project.name === snapshot.name);
  const summary = { name: snapshot.name, source_count: snapshot.source_count, bookmark_count: snapshot.bookmark_count, media_count: snapshot.media.length };
  if (index < 0) state.projects.push(summary); else state.projects[index] = summary;
  if (state.source && !currentSource()) { state.source = null; showView("sources"); }
  else render();
  return true;
}
function reconcilePending(snapshot) {
  for (const source of snapshot.sources) {
    const draft = draftFor(snapshot.name, source.name);
    if (draft.pending && source.bookmarks.some((mark) => mark.id === draft.pending.id)) {
      draft.raw = ""; draft.pending = null; draft.version += 1;
      toast("Bookmark confirmed on your PC.");
    }
    if (state.watchPending?.project === snapshot.name && state.watchPending.source === source.name
        && source.bookmarks.some((mark) => mark.id === state.watchPending.id)) {
      state.watchPending = null; toast("Bookmark confirmed on your PC.");
    }
  }
}
async function loadProjects() {
  const result = await request("/api/projects");
  state.projects = result.projects;
  render();
}
async function loadCurrent() {
  const project = state.project, version = ++state.loadVersion;
  const snapshot = await request(url("/api/project", { project }));
  if (project !== state.project || version !== state.loadVersion) return;
  installProject(snapshot); reconcilePending(snapshot);
  if (state.view === "player" && (!currentSource()?.available || state.loaded?.file !== currentSource().media_file)) showView("bookmarks");
  render();
}
async function acquireControl(takeover = false) {
  if (state.controlBusy || state.owned) return;
  state.controlBusy = true; updateControls();
  try {
    const result = await request(takeover ? "/api/controller/takeover" : "/api/controller/claim", { method: "POST", body: { page_id: state.page }, controller: false });
    state.epoch += 1; state.token = result.token; state.owned = true;
    $("connection").textContent = "Editor active"; $("connection").classList.add("live");
    $("gate").hidden = true; $("workspace").hidden = false; $("control-notice").hidden = true;
    await loadProjects();
    if (state.project) {
      try { await loadCurrent(); }
      catch (error) { if (error.code !== "unavailable") throw error; state.project = state.source = state.meta = null; state.view = "projects"; }
    } else if (state.remembered && state.projects.some((project) => project.name === state.remembered.project && !project.error)) {
      await openProject(state.remembered.project, state.remembered.source, false);
    }
    showView(state.view);
  } catch (error) {
    if (!state.owned && error.code === "network_error" && $("workspace").hidden) {
      showGate("Could not open the editor", error.message, { retry: true }); $("retry").textContent = "Try again";
    }
    handleError(error);
  } finally { state.controlBusy = false; updateControls(); }
}
async function exitEditor() {
  if (!state.owned || state.controlBusy || state.busy) return;
  state.controlBusy = true; updateControls();
  try {
    await request("/api/controller/release", { method: "POST", body: { page_id: state.page, token: state.token } });
    state.owned = false; state.token = null; state.epoch += 1; video.pause();
    for (const name of dialogs) if ($(`${name}-dialog`).open) $(`${name}-dialog`).close();
    $("connection").textContent = "Editor exited"; $("connection").classList.remove("live");
    showGate("Editor exited", "Control released. Enter the editor to resume this page.", { retry: true }); $("retry").textContent = "Enter Editor";
  } catch (error) {
    if (error.code === "network_error") toast("Exit Editor was not confirmed. Your entry and playback are kept; try again or take control from another page.", true);
    else handleError(error);
  } finally { state.controlBusy = false; updateControls(); }
}

function node(tag, text, className = "") { const element = document.createElement(tag); element.textContent = text; element.className = className; return element; }
function button(text, className, action) { const element = node("button", text, className); element.type = "button"; element.addEventListener("click", action); return element; }
function empty(container, message) { container.append(node("p", message, "empty")); }
function options(select, rows, selected, placeholder = null) {
  select.replaceChildren();
  if (placeholder !== null) { const choice = node("option", placeholder); choice.value = ""; select.append(choice); }
  for (const [value, label] of rows) { const choice = node("option", label); choice.value = value; select.append(choice); }
  select.value = selected || "";
}
function showView(view) {
  state.view = view; document.body.classList.toggle("player-open", view === "player");
  if (view !== "player") video.pause();
  for (const name of ["projects", "sources", "quick", "bookmarks", "player"]) $(`${name}-view`).hidden = name !== view;
  render(); window.scrollTo({ top: 0 });
}
function render() {
  $("project-context").textContent = state.project || "ON YOUR PC";
  $("back").hidden = state.view === "projects";
  $("back").textContent = state.view === "sources" ? "‹ Projects" : "‹ Sources";
  $("tabs").hidden = !currentSource() || !["quick", "bookmarks", "player"].includes(state.view);
  $("media-navigation").hidden = state.view !== "player";
  $("bookmark-count").textContent = String(currentSource()?.bookmarks.length || 0);
  for (const [id, view] of [["quick-tab", "quick"], ["bookmarks-tab", "bookmarks"], ["watch-tab", "player"]]) $(id).setAttribute("aria-current", state.view === view ? "page" : "false");
  if (state.view === "projects") renderProjects();
  if (state.view === "sources" && state.meta) renderSources();
  if (state.view === "quick" && currentSource()) renderQuick();
  if (state.view === "bookmarks" && currentSource()) renderBookmarks();
  if (state.view === "player" && currentSource()) renderWatch();
  updateControls();
}
function renderProjects() {
  const list = $("project-list"); list.replaceChildren();
  $("resume-quick").hidden = !state.remembered || !state.projects.some((project) => project.name === state.remembered.project);
  if (state.remembered) $("resume-quick").textContent = `Quick Log · ${state.remembered.project} · ${state.remembered.source}`;
  for (const project of state.projects) {
    const card = button("", "library-card", () => void openProject(project.name).catch(handleError));
    const text = node("span", "", "card-text"); text.append(node("span", project.name, "card-title"));
    text.append(node("span", project.error ? "Metadata needs attention" : projectCounts(project), "card-meta"));
    card.append(text, node("span", "›", "card-arrow")); list.append(card);
  }
  if (!state.projects.length) empty(list, "Create a project to start logging moments. No downloaded video is needed.");
}
function projectCounts(project) {
  return `${project.source_count} ${project.source_count === 1 ? "source" : "sources"} · ${project.bookmark_count} ${project.bookmark_count === 1 ? "bookmark" : "bookmarks"}`;
}
function renderSources() {
  const meta = state.meta; $("sources-title").textContent = meta.name;
  $("source-summary").textContent = projectCounts(meta);
  const list = $("source-list"); list.replaceChildren();
  for (const source of meta.sources) {
    const card = node("article", "", "source-card");
    const title = button(source.name, "source-title", () => chooseSource(source.name));
    const detail = node("p", `${source.bookmarks.length} bookmarks · ${source.available ? "MP4 ready" : source.media_file ? "Linked MP4 missing" : "No local MP4 needed"}`, "subtle");
    const actions = node("div", "", "source-actions");
    actions.append(button("Quick Log", "primary", () => chooseSource(source.name)), button("Bookmarks", "secondary", () => chooseSource(source.name, "bookmarks")));
    if (source.available) actions.append(button("Watch", "secondary", () => { chooseSource(source.name, "player"); }));
    const manage = button("Manage", "text-button write-action", () => openSourceDialog(source));
    manage.disabled = !state.owned || state.busy; actions.append(manage); card.append(title, detail, actions); list.append(card);
  }
  if (!meta.sources.length) empty(list, `Add ${meta.next_source_name}, or give your first source a custom name.`);
  $("local-media").hidden = !meta.media.length;
  const mediaList = $("local-media-list"); mediaList.replaceChildren();
  for (const file of meta.media) {
    const card = node("div", "", "local-file"); card.append(node("p", file.name, "card-title"));
    const watch = button("Watch", "secondary write-action", () => openLinkDialog(file.name)); watch.disabled = !state.owned || state.busy;
    card.append(watch); mediaList.append(card);
  }
}
async function openProject(name, restoreSource = null, focus = true) {
  const version = ++state.loadVersion;
  const snapshot = await request(url("/api/project", { project: name }));
  if (version !== state.loadVersion) return false;
  state.project = name; state.source = null; state.meta = snapshot; state.loadVersion += 1;
  if (restoreSource && snapshot.sources.some((source) => source.name === restoreSource)) { chooseSource(restoreSource, "quick", focus); }
  else showView("sources");
  return true;
}
function chooseSource(name, view = "quick", focus = true) {
  if (!state.meta?.sources.some((source) => source.name === name)) return;
  if (state.source !== name) $("quick-message").hidden = true;
  state.source = name; remember();
  if (view === "player") openWatch();
  else { showView(view); if (view === "quick" && focus) focusQuick(); }
}
function focusQuick() { $("quick-time").focus(); $("quick-time").select(); }
function renderQuick() {
  options($("quick-project"), state.projects.filter((project) => !project.error).map((project) => [project.name, project.name]), state.project);
  options($("quick-source"), state.meta.sources.map((source) => [source.name, source.name]), state.source);
  const draft = draftFor(); if ($("quick-time").value !== draft.raw) $("quick-time").value = draft.raw;
  $("quick-count").textContent = `${currentSource().bookmarks.length} bookmarks · ${currentSource().name}`;
  updateQuickPreview();
}
function updateQuickPreview() {
  const raw = $("quick-time").value;
  try {
    $("quick-preview").textContent = raw.trim() ? `${raw.trim()} → ${formatBookmark(parseTimestamp(raw))}` : "1742 → 17:42 · colons work too";
    $("quick-preview").classList.remove("invalid"); $("quick-time").setAttribute("aria-invalid", "false");
  } catch (error) { $("quick-preview").textContent = error.message; $("quick-preview").classList.add("invalid"); $("quick-time").setAttribute("aria-invalid", "true"); }
}
async function saveQuick(event) {
  event.preventDefault(); if (state.busy || state.controlBusy || !state.owned || !currentSource()) return;
  let time;
  try { time = parseTimestamp($("quick-time").value); }
  catch (error) { fieldError("quick-message", error); $("quick-time").setAttribute("aria-invalid", "true"); focusQuick(); return; }
  const project = state.project, source = state.source, draft = draftFor();
  draft.raw = $("quick-time").value;
  const version = draft.version, raw = draft.raw;
  const pending = draft.pending?.time === time && draft.pending.raw === raw ? draft.pending : { id: newId(), time, raw };
  draft.pending = pending;
  await mutate(async () => {
    const result = await request(url("/api/bookmarks", { project, source }), { method: "POST", body: { id: pending.id, time } });
    installProject(result);
    if (draft.version === version) { draft.raw = ""; draft.pending = null; draft.version += 1; }
    if (project === state.project && source === state.source && state.view === "quick") {
      renderQuick(); $("quick-message").hidden = false; $("quick-message").textContent = `Saved ${formatBookmark(time)} on your PC.`;
      $("quick-message").classList.remove("invalid"); focusQuick();
    }
    if (project !== state.project || source !== state.source || state.view !== "quick") toast(`Saved bookmark · ${formatBookmark(time)}`);
  }, (error) => { fieldError("quick-message", error); $("quick-message").classList.add("invalid"); handleError(error); });
}
function renderBookmarks() {
  const source = currentSource(), list = $("bookmark-list"); list.replaceChildren();
  $("bookmarks-title").textContent = source.name;
  $("bookmarks-detail").textContent = `${source.bookmarks.length} bookmarks · ${source.available ? "Tap a time to watch from that moment." : "Log and edit times without local media. Link an MP4 from Sources when ready."}`;
  for (const mark of source.bookmarks) {
    const card = node("article", "", "bookmark-card");
    const jump = button(formatBookmark(mark.time), "bookmark-jump", () => openWatch(mark.time)); jump.disabled = !source.available || !state.owned;
    const actions = node("div", "", "bookmark-actions");
    const edit = button("Edit", "text-button write-action", () => editBookmark(mark));
    const remove = button("Delete", "text-button delete-button write-action", () => confirmDelete("bookmark", mark));
    edit.disabled = remove.disabled = !state.owned || state.busy; actions.append(edit, remove); card.append(jump, actions); list.append(card);
  }
  if (!source.bookmarks.length) empty(list, "No moments logged yet. Open Quick Log, or bookmark while watching a linked MP4.");
}
function renderWatch() {
  const source = currentSource(), playable = state.meta.sources.filter((row) => row.available), index = playable.findIndex((row) => row.name === source.name);
  $("media-title").textContent = `${source.name} · ${source.media_file}`;
  $("media-title").title = $("media-title").textContent;
  $("media-index").textContent = `Video ${index + 1} of ${playable.length}`;
  $("previous").disabled = index <= 0; $("next").disabled = index < 0 || index >= playable.length - 1;
  const pending = state.watchPending;
  $("watch-save-error").hidden = !pending;
  if (pending) $("watch-save-message").textContent = `${pending.source} · ${formatBookmark(pending.time)} not confirmed. Refresh Bookmarks to check, or retry.`;
}
function openWatch(time = null) {
  const source = currentSource(); if (!source?.available || !state.owned) return;
  const changed = state.loaded?.project !== state.project || state.loaded?.file !== source.media_file;
  showView("player"); $("video-error").hidden = true;
  if (changed || !video.getAttribute("src")) {
    state.ready = false; state.pendingSeek = time ?? 0;
    state.loaded = { project: state.project, file: source.media_file };
    video.src = url("/media", { file: source.media_file }); video.load();
    $("current-time").textContent = "0:00.000"; $("duration").textContent = "—";
  } else if (time !== null) seekBookmark(time);
  updateControls();
  if (time !== null) void video.play().catch(() => toast("Tap Play to watch from this bookmark."));
}
function seekBookmark(time) {
  if (time > video.duration) toast("This bookmark is beyond the linked MP4. Showing its end; check the source's video association.", true);
  seek(time);
}
function updateTime() { $("current-time").textContent = formatTime(video.currentTime); if (!state.dragging) $("scrubber").value = String(video.currentTime); }
function seek(time) { if (!state.ready) return; video.currentTime = clampSeek(time, video.duration); updateTime(); }
async function saveWatch(retry = false) {
  if (!state.owned || state.busy || state.controlBusy || (!retry && (!state.ready || !currentSource()))) return;
  if (!retry && state.watchPending) return;
  const pending = retry ? state.watchPending : { project: state.project, source: state.source, id: newId(), time: video.currentTime };
  if (!pending) return;
  state.watchPending = pending;
  await mutate(async () => {
    const result = await request(url("/api/bookmarks", { project: pending.project, source: pending.source }), { method: "POST", body: { id: pending.id, time: pending.time } });
    state.watchPending = null; installProject(result); toast(`Saved bookmark · ${formatBookmark(pending.time)}`);
  }, (error) => { renderWatch(); handleError(error); });
}
function updateControls() {
  const write = state.owned && !state.busy && !state.controlBusy;
  for (const id of ["new-project", "project-save", "new-source", "quick-add-source", "source-save", "source-remove", "link-save", "edit-save", "confirm-save", "next-episode", "quick-save"]) $(id).disabled = !write;
  for (const element of document.querySelectorAll(".write-action")) element.disabled = !write;
  $("new-source").disabled ||= !state.meta;
  $("quick-save").disabled ||= !currentSource();
  $("next-episode").disabled ||= !currentSource();
  $("quick-project").disabled = $("quick-source").disabled = state.busy || state.controlBusy;
  $("exit-editor").hidden = !state.owned; $("exit-editor").disabled = state.busy || state.controlBusy;
  for (const id of ["retry", "gate-take-control", "take-control"]) $(id).disabled = state.controlBusy;
  for (const id of ["play", "scrubber"]) $(id).disabled = !state.ready;
  for (const element of document.querySelectorAll("[data-skip], [data-rate]")) element.disabled = !state.ready;
  $("bookmark").disabled = !write || !state.ready || !currentSource() || Boolean(state.watchPending);
  $("watch-retry").disabled = !write || !state.watchPending;
  $("watch-tab").disabled = !currentSource()?.available;
  for (const name of dialogs) $(`${name}-cancel`).disabled = state.busy;
}

function openSourceDialog(source = null) {
  if (!state.owned || !state.meta || state.busy) return;
  state.sourceDialog = { project: state.project, original: source?.name || null, revision: state.meta.revision };
  $("source-dialog-title").textContent = source ? "Manage source" : "New source";
  $("source-name").value = source?.name || state.meta.next_source_name;
  const media = state.meta.media.map((file) => [file.name, file.name]);
  if (source?.media_file && !media.some(([name]) => name === source.media_file)) media.push([source.media_file, `${source.media_file} · missing`]);
  options($("source-media"), media, source?.media_file || "", "No local MP4");
  $("source-error").hidden = $("source-existing").hidden = true; $("source-remove").hidden = !source;
  $("source-dialog").showModal(); $("source-name").focus(); $("source-name").select();
}
function openLinkDialog(file) {
  if (!state.owned || state.busy) return;
  state.linking = { project: state.project, file, revision: state.meta.revision };
  $("link-file").textContent = file;
  options($("link-source"), state.meta.sources.map((source) => [source.name, source.name]), state.source, "Create a new source");
  $("link-name").value = state.meta.next_source_name; $("link-error").hidden = true; updateLink(); $("link-dialog").showModal();
}
function updateLink() { const create = !$("link-source").value; $("link-name").hidden = $("link-name-label").hidden = !create; $("link-name").required = create; }
function editBookmark(mark) {
  state.editing = { ...mark, project: state.project, source: state.source, revision: state.meta.revision, raw: compactTimestamp(mark.time) };
  $("edit-source").textContent = state.source; $("edit-time").value = state.editing.raw; $("edit-error").hidden = true;
  $("edit-dialog").showModal(); $("edit-time").focus(); $("edit-time").select();
}
function confirmDelete(kind, mark = null) {
  state.confirming = { kind, project: state.project, source: kind === "source" ? state.sourceDialog.original : state.source, id: mark?.id, revision: state.meta.revision };
  $("source-dialog").close(); $("confirm-error").hidden = true;
  $("confirm-title").textContent = kind === "source" ? "Remove this source?" : "Delete this bookmark?";
  $("confirm-detail").textContent = kind === "source" ? `${state.confirming.source} and all its bookmarks will be removed. Its MP4 stays on your PC.` : `${state.source} · ${formatBookmark(mark.time)}`;
  $("confirm-dialog").showModal();
}

$("retry").addEventListener("click", () => void acquireControl());
for (const id of ["gate-take-control", "take-control"]) $(id).addEventListener("click", () => void acquireControl(true));
$("exit-editor").addEventListener("click", exitEditor);
$("refresh-projects").addEventListener("click", () => void loadProjects().catch(handleError));
for (const id of ["refresh-sources", "refresh-bookmarks"]) $(id).addEventListener("click", () => void loadCurrent().catch(handleError));
$("resume-quick").addEventListener("click", () => void openProject(state.remembered.project, state.remembered.source).catch(handleError));
$("back").addEventListener("click", () => {
  if (state.view === "sources") { state.project = state.source = state.meta = null; showView("projects"); void loadProjects().catch(handleError); }
  else showView("sources");
});
for (const id of ["quick-tab", "watch-quick"]) $(id).addEventListener("click", () => { showView("quick"); focusQuick(); });
$("bookmarks-tab").addEventListener("click", () => { showView("bookmarks"); void loadCurrent().catch(handleError); });
$("watch-tab").addEventListener("click", () => openWatch());
$("quick-project").addEventListener("change", () => {
  const name = $("quick-project").value;
  void openProject(name, state.projects.some((project) => project.name === name) && state.remembered?.project === name ? state.remembered.source : null).then((opened) => {
    if (!opened) return;
    if (state.view === "sources" && state.meta.sources.length) chooseSource(state.meta.sources[0].name);
  }).catch(handleError);
});
$("quick-source").addEventListener("change", () => { $("quick-message").hidden = true; chooseSource($("quick-source").value); });
$("quick-time").addEventListener("input", () => { const draft = draftFor(); draft.raw = $("quick-time").value; draft.version += 1; draft.pending = null; $("quick-message").hidden = true; updateQuickPreview(); });
$("quick-form").addEventListener("submit", saveQuick);
$("next-episode").addEventListener("click", () => {
  const source = currentSource(); if (!source) return;
  const project = state.project, name = source.next_episode_name;
  void mutate(async () => {
    try { const result = await request(url("/api/sources"), { method: "POST", revision: state.meta.revision, body: { name, media_file: null } }); installProject(result); }
    catch (error) { if (error.code !== "source_exists") throw error; chooseSource(error.source); return; }
    if (state.project === project) chooseSource(name);
  });
});
$("new-project").addEventListener("click", () => { $("project-name").value = ""; $("project-error").hidden = true; $("project-dialog").showModal(); $("project-name").focus(); });
$("project-form").addEventListener("submit", (event) => {
  event.preventDefault(); void mutate(async () => {
    const result = await request("/api/projects", { method: "POST", body: { name: $("project-name").value } });
    state.project = result.name; state.source = null; installProject(result); $("project-dialog").close(); showView("sources"); toast("Project created on your PC.");
  }, (error) => { fieldError("project-error", error); handleError(error); });
});
for (const id of ["new-source", "quick-add-source"]) $(id).addEventListener("click", () => openSourceDialog());
$("source-form").addEventListener("submit", (event) => {
  event.preventDefault(); const context = state.sourceDialog;
  void mutate(async () => {
    const name = $("source-name").value.trim();
    const result = await request(url(context.original ? "/api/source" : "/api/sources", { project: context.project, ...(context.original ? { source: context.original } : {}) }),
      { method: context.original ? "PATCH" : "POST", revision: context.revision, body: { name, media_file: $("source-media").value || null } });
    if (context.original) {
      const old = draftFor(context.project, context.original);
      state.drafts.set(JSON.stringify([context.project, name]), old);
      if (name !== context.original) state.drafts.delete(JSON.stringify([context.project, context.original]));
      if (state.source === context.original) state.source = name;
      if (state.watchPending?.project === context.project && state.watchPending.source === context.original) state.watchPending.source = name;
    }
    installProject(result); $("source-dialog").close(); chooseSource(name); toast(context.original ? "Source saved." : "Source added.");
  }, (error) => { fieldError("source-error", error); state.conflictSource = error.source; $("source-existing").hidden = error.code !== "source_exists"; handleError(error); });
});
$("source-existing").addEventListener("click", () => { const name = state.conflictSource; $("source-dialog").close(); void loadCurrent().then(() => chooseSource(name)).catch(handleError); });
$("source-remove").addEventListener("click", () => confirmDelete("source"));
$("link-source").addEventListener("change", updateLink);
$("link-form").addEventListener("submit", (event) => {
  event.preventDefault(); const context = state.linking;
  void mutate(async () => {
    let name = $("link-source").value || $("link-name").value.trim();
    const existing = Boolean($("link-source").value);
    let result;
    try { result = await request(url(existing ? "/api/source" : "/api/sources", { project: context.project, ...(existing ? { source: name } : {}) }), { method: existing ? "PATCH" : "POST", revision: context.revision, body: { name, media_file: context.file } }); }
    catch (error) {
      if (error.code !== "source_exists") throw error;
      name = error.source; options($("link-source"), state.meta.sources.map((source) => [source.name, source.name]), name, "Create a new source"); updateLink();
      throw new ApiError(`${name} already exists. Select it to link this video.`, "source_exists");
    }
    installProject(result); $("link-dialog").close(); chooseSource(name, "player");
  }, (error) => { fieldError("link-error", error); handleError(error); });
});
$("edit-form").addEventListener("submit", (event) => {
  event.preventDefault(); const row = state.editing;
  void mutate(async () => {
    const raw = $("edit-time").value, time = raw === row.raw ? row.time : parseTimestamp(raw);
    installProject(await request(url(`/api/bookmarks/${row.id}`, { project: row.project, source: row.source }), { method: "PATCH", revision: row.revision, body: { time } }));
    $("edit-dialog").close(); toast("Bookmark time saved.");
  }, (error) => { fieldError("edit-error", error); handleError(error); });
});
$("confirm-form").addEventListener("submit", (event) => {
  event.preventDefault(); const row = state.confirming;
  void mutate(async () => {
    installProject(await request(url(row.kind === "source" ? "/api/source" : `/api/bookmarks/${row.id}`, { project: row.project, source: row.source }), { method: "DELETE", revision: row.revision }));
    if (row.kind === "source") {
      state.drafts.delete(JSON.stringify([row.project, row.source]));
      if (state.watchPending?.project === row.project && state.watchPending.source === row.source) state.watchPending = null;
      if (state.remembered?.project === row.project && state.remembered.source === row.source) {
        state.remembered = null;
        try { localStorage.removeItem(preferenceKey); } catch { /* Optional convenience. */ }
      }
    }
    $("confirm-dialog").close(); if (!currentSource()) showView("sources"); toast(row.kind === "source" ? "Source and bookmarks removed." : "Bookmark deleted.");
  }, (error) => { fieldError("confirm-error", error); handleError(error); });
});
for (const name of dialogs) {
  $(`${name}-cancel`).addEventListener("click", () => $(`${name}-dialog`).close());
  $(`${name}-dialog`).addEventListener("cancel", (event) => { if (state.busy) event.preventDefault(); });
}
$("watch-retry").addEventListener("click", () => void saveWatch(true));
$("watch-dismiss").addEventListener("click", () => { state.watchPending = null; render(); });
$("bookmark").addEventListener("click", () => void saveWatch());
$("play").addEventListener("click", () => { if (video.paused) void video.play().catch(() => toast("Safari could not play this MP4. Check the file and connection.", true)); else video.pause(); });
for (const name of ["play", "pause", "ended"]) video.addEventListener(name, () => { $("play").textContent = video.paused ? "Play" : "Pause"; });
video.addEventListener("loadedmetadata", () => {
  state.ready = Number.isFinite(video.duration) && video.duration > 0; $("duration").textContent = formatTime(video.duration); $("scrubber").max = String(video.duration);
  if (state.pendingSeek !== null && state.ready) { seekBookmark(state.pendingSeek); state.pendingSeek = null; }
  syncRate(); updateControls(); updateTime();
});
video.addEventListener("emptied", () => { state.ready = false; updateControls(); });
video.addEventListener("timeupdate", updateTime);
video.addEventListener("error", () => { state.ready = false; updateControls(); $("video-error").textContent = "Cannot play this MP4. Check the PC connection and prepared H.264 video with compatible audio."; $("video-error").hidden = false; });
for (const element of document.querySelectorAll("[data-skip]")) element.addEventListener("click", () => seek(video.currentTime + Number(element.dataset.skip)));
$("scrubber").addEventListener("pointerdown", () => { state.dragging = true; }); $("scrubber").addEventListener("input", () => seek(Number($("scrubber").value)));
for (const event of ["change", "pointerup", "pointercancel"]) $("scrubber").addEventListener(event, () => { state.dragging = false; updateTime(); });
function syncRate() {
  let matched = false;
  for (const element of document.querySelectorAll("[data-rate]")) { const selected = Math.abs(Number(element.dataset.rate) - video.playbackRate) < .001; element.setAttribute("aria-pressed", String(selected)); matched ||= selected; }
  $("actual-speed").hidden = matched; $("actual-speed").textContent = `${video.playbackRate}× actual`;
}
video.addEventListener("ratechange", syncRate);
for (const element of document.querySelectorAll("[data-rate]")) element.addEventListener("click", () => {
  if (!state.ready) return;
  const requested = Number(element.dataset.rate), result = acceptedRate(video, requested); syncRate();
  $("speed-notice").hidden = result.accepted; $("speed-notice").textContent = `Safari did not accept ${requested}×. Playing at ${result.rate}×.`;
});
for (const [id, offset] of [["previous", -1], ["next", 1]]) $(id).addEventListener("click", () => {
  const playable = state.meta.sources.filter((source) => source.available), index = playable.findIndex((source) => source.name === state.source);
  if (playable[index + offset]) chooseSource(playable[index + offset].name, "player");
});

void acquireControl();
