function assert(condition, message) { if (!condition) throw new Error(message); }
function equal(actual, expected, message) { assert(actual === expected, `${message}: ${actual} !== ${expected}`); }
function setup() {
  Object.assign(state, { project: "A show – 日本語", file: "[Any name] # café.mp4", files: [{ name: "[Any name] # café.mp4" }],
    owned: true, ready: true, token: "live-token", in: null, out: null, saving: false, stopAt: null,
    view: "player", controlBusy: false, dialogBusy: false, selections: [], revision: "initial" });
  Object.assign(fakeVideo, { paused: false, pauseCalls: 0, currentTime: 50.125, duration: 120.5, playbackRate: 1 });
  element("workspace").hidden = false; element("gate").hidden = true; element("control-notice").hidden = true; element("toast").hidden = true;
  showView("player"); updateControls();
}
function reply(payload, ok = true) { return { ok, json: async () => payload }; }
function libraryReply(path, token = "new-controller-token") {
  if (path.startsWith("/api/controller/")) return reply({ token });
  if (path.startsWith("/api/project?")) return reply({ media: state.files });
  if (path.startsWith("/api/selections?")) return reply({ revision: "fresh", selections: state.selections });
  if (path === "/api/projects") return reply({ projects: [] });
  throw new Error(`Unexpected request: ${path}`);
}
async function checks() {
  equal(formatTime(502.25), "8:22.250", "fractional display");
  equal(formatTime(3599.9996), "1:00:00.000", "rounding carries into hours");
  equal(formatTime(null), "—", "unmarked time");
  equal(clampSeek(-2, 100), 0, "seek before start");
  equal(clampSeek(120, 100), 100, "seek past end");
  let rejected = { get playbackRate() { return 1; }, set playbackRate(value) { throw new Error("unsupported"); } };
  equal(acceptedRate(rejected, 3).accepted, false, "rejected rate");
  let ignored = { get playbackRate() { return 0.5; }, set playbackRate(value) {} };
  equal(acceptedRate(ignored, 3).rate, 0.5, "show actual rate when ignored");
  equal(acceptedRate(fakeVideo, 0.25).accepted, true, "accepted quarter speed");
  assert(newId() !== newId(), "page identities are unique");

  Object.assign(state, { owned: false, token: null, project: null, file: null, view: "library" });
  element("workspace").hidden = true;
  const acquisitionPaths = [];
  transport = async path => { acquisitionPaths.push(path); return libraryReply(path); };
  await acquireControl();
  equal(acquisitionPaths.join(","), "/api/controller/claim,/api/projects", "opening automatically claims and loads library");
  equal(state.owned, true, "first page owns the editor");
  equal(state.token, "new-controller-token", "claim installs its opaque token");
  equal(intervalCalls, 0, "acquisition starts no periodic requests");

  state.owned = false; state.token = null; element("workspace").hidden = true;
  const blockedPaths = [];
  transport = async path => { blockedPaths.push(path); return reply({ error: { code: "controller_occupied", message: "Clip Selector is open elsewhere" } }, false); };
  await acquireControl();
  equal(blockedPaths.join(","), "/api/controller/claim", "occupied page never automatically takes over");
  equal(element("gate-title").textContent, "Clip Selector is open elsewhere", "second page sees the occupied screen");
  equal(element("gate-take-control").hidden, false, "second page can explicitly Take Control");
  const takeoverPaths = [];
  transport = async path => { takeoverPaths.push(path); return libraryReply(path, "forced-controller-token"); };
  await element("gate-take-control").listeners.click[0]();
  equal(takeoverPaths[0], "/api/controller/takeover", "only the Take Control tap forces acquisition");
  equal(state.token, "forced-controller-token", "explicit takeover installs the new token");
  state.controlBusy = true;
  await acquireControl(true);
  equal(takeoverPaths.length, 2, "busy controller action is ignored without queuing a retry");
  state.controlBusy = false;

  setup(); state.in = 10.25; state.out = 90.875;
  let lifecycleCalls = 0;
  transport = async () => { lifecycleCalls++; throw new Error("unexpected lifecycle request"); };
  document.hidden = true; document.dispatchEvent({ type: "visibilitychange" });
  for (const type of ["pagehide", "offline", "online", "pageshow"]) window.dispatchEvent({ type, persisted: true });
  document.hidden = false; document.dispatchEvent({ type: "visibilitychange" });
  equal(lifecycleCalls, 0, "visibility, page termination, and network events send no requests");
  equal(state.owned, true, "ownership survives browser lifecycle events");
  equal(fakeVideo.pauseCalls, 0, "lifecycle events never pause video");
  equal(fakeVideo.currentTime, 50.125, "lifecycle events preserve playback position");
  equal(element("workspace").hidden, false, "lifecycle events keep the player visible");
  equal(state.in, 10.25, "lifecycle events preserve IN"); equal(state.out, 90.875, "lifecycle events preserve OUT");

  setup();
  updateControls();
  for (const button of fakeRates) {
    button.listeners.click[0]();
    equal(fakeVideo.playbackRate, Number(button.dataset.rate), "speed tap changes playback rate");
    equal(element("speed-notice").hidden, true, "accepted speeds do not show a warning below the video");
    equal(button.getAttribute("aria-pressed"), "true", "accepted speed is selected");
    equal(fakeRates.filter(node => node.getAttribute("aria-pressed") === "true").length, 1, "only the accepted speed is selected");
  }
  equal(fakeVideo.pauseCalls, 0, "changing speed keeps playback running");
  fakeVideo.playbackRate = 1.5;
  fakeVideo.listeners.ratechange[0]();
  equal(element("actual-speed").hidden, false, "external unsupported preset remains visible");
  equal(element("actual-speed").textContent, "1.5× actual", "external native speed is reported");
  assert(fakeRates.every(node => node.getAttribute("aria-pressed") === "false"), "no incorrect preset is selected");
  Object.defineProperty(fakeVideo, "playbackRate", { configurable: true, get() { return 1; }, set(value) { throw new Error("unsupported"); } });
  fakeRates[4].listeners.click[0]();
  equal(fakeRates[2].getAttribute("aria-pressed"), "true", "rejected speed retains actual normal rate");
  equal(element("speed-notice").hidden, false, "rejected speed has visible feedback");
  Object.defineProperty(fakeVideo, "playbackRate", { configurable: true, writable: true, value: 1 });
  fakeSkips[0].listeners.click[0]();
  equal(fakeVideo.currentTime, 45.125, "back five seconds keeps precision");
  fakeSkips[1].listeners.click[0]();
  equal(fakeVideo.currentTime, 50.125, "forward five seconds keeps precision");
  showView("player");
  assert(document.body.classList.contains("player-open"), "editing activates the compact landscape layout");
  equal(element("media-navigation").hidden, false, "video navigation is available while editing");
  showView("selections");
  assert(!document.body.classList.contains("player-open"), "selections returns to the browsing layout");
  equal(element("media-navigation").hidden, true, "video navigation is hidden outside the player");
  setup();
  loseControl("Editor control was transferred to another page");
  equal(element("capture").disabled, true, "control loss disables writes");
  assert([...fakeRates, ...fakeSkips].every(button => !button.disabled), "control loss leaves playback controls available");
  equal(fakeVideo.pauseCalls, 0, "control loss does not pause playback");
  equal(element("workspace").hidden, false, "control loss keeps the player visible");
  equal(element("control-notice").hidden, false, "control loss offers an explicit takeover");

  setup();
  let sent;
  transport = async (path, options) => {
    sent = { path, ...options, body: JSON.parse(options.body) };
    // Playback advances while the PC processes the capture.
    fakeVideo.currentTime = 60.75;
    return { ok: true, json: async () => ({ revision: "saved", selections: [{ id: sent.body.id, file: state.file, start: 35.125, end: 65.125, available: true }] }) };
  };
  await save("capture");
  equal(sent.body.time, 50.125, "capture samples fractional currentTime before network");
  equal(fakeVideo.pauseCalls, 0, "capture never pauses playback");
  equal(fakeVideo.paused, false, "capture continues playback");
  equal(state.selections[0].start, 35.125, "capture installs confirmed server result");
  assert(element("toast").textContent.startsWith("Saved"), "confirmed save message");
  equal(sent.headers["X-Page-Id"], state.page, "save carries page identity");
  equal(sent.headers["X-Controller-Token"], state.token, "save carries token");
  assert(sent.path.includes(encodeURIComponent(state.project)), "Unicode project identity is encoded");

  setup(); state.in = 10.25; state.out = 90.875;
  transport = async (path, options) => {
    sent = JSON.parse(options.body);
    // User marks a new range while the old one is being persisted.
    state.in = 95;
    return { ok: true, json: async () => ({ revision: "manual", selections: [{ ...sent, available: true }] }) };
  };
  await save("range");
  equal(sent.start, 10.25, "manual IN"); equal(sent.end, 90.875, "manual OUT");
  equal(state.in, 95, "new IN is not cleared by previous save");
  equal(fakeVideo.pauseCalls, 0, "manual save never pauses");
  state.in = 100; state.out = 2;
  let calls = 0; transport = async () => { calls++; };
  await save("range"); equal(calls, 0, "invalid manual range never submitted");

  setup();
  transport = async () => ({ ok: false, json: async () => ({ error: { code: "storage_error", message: "Disk full; not saved." } }) });
  await save("capture"); equal(element("toast").textContent, "Disk full; not saved.", "failed save is visible");
  equal(state.saving, false, "controls recover from save failure");

  setup(); state.in = 10.25; state.out = 90.875;
  let failedCalls = 0;
  transport = async () => { failedCalls++; throw new Error("network timeout"); };
  await save("range");
  equal(failedCalls, 1, "uncertain save is never retried");
  equal(state.owned, true, "network failure does not revoke ownership");
  equal(state.ready, true, "network failure preserves media readiness");
  equal(element("workspace").hidden, false, "network failure leaves player visible");
  equal(fakeVideo.pauseCalls, 0, "network failure does not pause playback");
  equal(fakeVideo.currentTime, 50.125, "network failure preserves playback position");
  equal(state.in, 10.25, "uncertain save preserves IN"); equal(state.out, 90.875, "uncertain save preserves OUT");
  equal(state.revision, "initial", "uncertain save never installs a confirmed revision");
  assert(element("toast").classList.contains("error"), "uncertain save displays an error");
  assert(element("toast").textContent.includes("Cannot confirm"), "uncertain save does not claim success");

  setup();
  editSelection({ id: "editing-selection-identity", file: state.file, start: 20.25, end: 80.875, available: true });
  transport = async () => { throw new Error("temporary network failure"); };
  await changeSelection({ preventDefault() {} }, "edit");
  equal(element("edit-dialog").open, true, "failed adjustment keeps the dialog open");
  equal(element("edit-start").value, "20.25", "failed adjustment preserves input");
  equal(element("edit-error").hidden, false, "failed adjustment displays its error");
  equal(fakeVideo.pauseCalls, 0, "failed adjustment introduces no playback pause");
  element("edit-dialog").close();

  setup(); state.in = 10.25; state.out = 90.875;
  let transferredCalls = 0;
  transport = async () => { transferredCalls++; return reply({ error: { code: "controller_transferred", message: "Editor control was transferred to another page" } }, false); };
  await save("capture");
  equal(transferredCalls, 1, "rejected stale save never silently reclaims control");
  equal(state.owned, false, "stale controller loses edit authority");
  equal(element("control-message").textContent, "Editor control was transferred to another page", "takeover is clearly explained");
  equal(element("control-notice").hidden, false, "previous controller is offered Take Control");
  equal(element("capture").disabled, true, "stale controller cannot capture");
  equal(fakeVideo.pauseCalls, 0, "takeover rejection does not pause video");
  equal(state.in, 10.25, "takeover rejection preserves unfinished IN");
  const restoringPaths = [];
  transport = async path => { restoringPaths.push(path); return libraryReply(path); };
  await element("take-control").listeners.click[0]();
  equal(restoringPaths[0], "/api/controller/takeover", "previous owner takes control only with another tap");
  equal(fakeVideo.pauseCalls, 0, "explicit takeover keeps current playback running");
  equal(fakeVideo.currentTime, 50.125, "explicit takeover preserves playback position");
  equal(state.in, 10.25, "explicit takeover preserves unfinished IN");
  equal(element("control-notice").hidden, true, "successful takeover removes notice");

  setup(); state.in = 10.25; state.out = 90.875;
  transport = async () => { throw new Error("release response lost"); };
  await exitEditor();
  equal(state.owned, true, "unconfirmed release does not claim a successful exit");
  equal(fakeVideo.pauseCalls, 0, "failed exit leaves playback running");
  equal(element("workspace").hidden, false, "failed exit leaves player visible");
  let releaseRequest;
  transport = async (path, options) => { releaseRequest = { path, body: JSON.parse(options.body) }; return reply({ released: true }); };
  await element("exit-editor").listeners.click[0]();
  equal(releaseRequest.path, "/api/controller/release", "Exit Editor explicitly releases");
  equal(releaseRequest.body.token, "live-token", "release requires the current opaque token");
  equal(state.owned, false, "confirmed exit clears local edit authority");
  equal(state.token, null, "confirmed exit clears local token");
  equal(fakeVideo.pauseCalls, 1, "explicit exit pauses only after confirmed release");
  equal(element("gate-title").textContent, "Editor exited", "confirmed exit shows its resume screen");
  equal(element("retry").textContent, "Enter Editor", "user can enter editing again");
  transport = async path => libraryReply(path, "reentered-token");
  await element("retry").listeners.click[0]();
  equal(state.owned, true, "Enter Editor reacquires normally");
  equal(state.token, "reentered-token", "reentry uses a new token");
  equal(fakeVideo.currentTime, 50.125, "reentry preserves current playback position");
  equal(state.in, 10.25, "reentry preserves unfinished marks");

  setup();
  let finish;
  transport = () => new Promise(resolve => { finish = resolve; });
  const pending = save("capture");
  loseControl("Editor control was transferred to another page");
  finish({ ok: true, json: async () => ({ revision: "late", selections: [] }) });
  await pending;
  equal(state.owned, false, "known takeover disables authority");
  assert(state.revision !== "late", "late response from old session never installs stale data");

  setup();
  let failLate;
  transport = () => new Promise((resolve, reject) => { failLate = reject; });
  const oldRequest = request("/api/projects").catch(error => error);
  loseControl("Editor control was transferred to another page");
  state.owned = true; state.token = "new-live-token";
  failLate(new Error("old network timeout"));
  const oldError = await oldRequest;
  equal(oldError.code, "session_changed", "old failed network request is ignored after explicit reacquisition");
  handleError(oldError); equal(state.owned, true, "old network error never revokes the new session");

  setup();
  state.stopAt = 12; fakeVideo.currentTime = 12.25;
  updateTime(); equal(fakeVideo.paused, true, "replay stops at OUT"); equal(fakeVideo.currentTime, 12, "replay clamps OUT");
  state.stopAt = 30; seek(60); equal(state.stopAt, null, "manual seeking exits bounded replay");
  equal(fakeVideo.currentTime, 60, "seek control");

  equal(intervalCalls, 0, "all ownership actions run without periodic network monitoring");
  assert(timerDelays.every(delay => [12000, 2600, 8000].includes(delay)), "only request deadlines and toast dismissal use timers");
}
checks().then(() => {
  if (typeof print === "function") print("Frontend behavior checks passed");
  else console.log("Frontend behavior checks passed");
}).catch(error => {
  if (typeof print === "function") { print(String(error.stack || error)); quit(1); }
  else { console.error(error); process.exit(1); }
});
