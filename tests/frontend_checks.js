function assert(condition, message) { if (!condition) throw new Error(message); }
function equal(actual, expected, message) { assert(actual === expected, `${message}: ${actual} !== ${expected}`); }
function setup() {
  Object.assign(state, { project: "A show – 日本語", file: "[Any name] # café.mp4", files: [{ name: "[Any name] # café.mp4" }],
    owned: true, ready: true, token: "live-token", in: null, out: null, saving: false, stopAt: null });
  Object.assign(fakeVideo, { paused: false, pauseCalls: 0, currentTime: 50.125, duration: 120.5, playbackRate: 1 });
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

  setup();
  updateControls();
  for (const button of fakeRates) {
    button.listeners.click[0]();
    equal(fakeVideo.playbackRate, Number(button.dataset.rate), "speed tap changes playback rate");
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
  disconnect("Disconnected", "Connection lost");
  assert([...fakeRates, ...fakeSkips].every(button => button.disabled), "transport disables on lease loss");
  fakeRates[0].listeners.click[0]();
  equal(fakeVideo.playbackRate, 1, "disabled rate cannot change playback");

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
  equal(sent.headers["X-Lease-Token"], state.token, "save carries token");
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

  setup();
  let finish;
  transport = () => new Promise(resolve => { finish = resolve; });
  const pending = save("capture");
  disconnect("Reconnecting", "Controller must be checked again.");
  finish({ ok: true, json: async () => ({ revision: "late", selections: [] }) });
  await pending;
  equal(state.owned, false, "suspension disables authority");
  assert(state.revision !== "late", "late response from old session never installs stale data");

  setup();
  let failLate;
  transport = () => new Promise((resolve, reject) => { failLate = reject; });
  const oldRequest = request("/api/projects").catch(error => error);
  disconnect("Reconnecting", "Session changed");
  state.owned = true; state.token = "new-live-token";
  failLate(new Error("old network timeout"));
  const oldError = await oldRequest;
  equal(oldError.code, "session_changed", "old failed network request is ignored after reconnect");
  handleError(oldError); equal(state.owned, true, "old network error never disconnects the new session");

  setup();
  state.stopAt = 12; fakeVideo.currentTime = 12.25;
  updateTime(); equal(fakeVideo.paused, true, "replay stops at OUT"); equal(fakeVideo.currentTime, 12, "replay clamps OUT");
  state.stopAt = 30; seek(60); equal(state.stopAt, null, "manual seeking exits bounded replay");
  equal(fakeVideo.currentTime, 60, "seek control");

  setup();
  state.claimBusy = true; state.reconnectQueued = false;
  await connect(); equal(state.reconnectQueued, true, "resume queues a reclaim if earlier claim is in flight");
  state.claimBusy = false;
}
checks().then(() => {
  if (typeof print === "function") print("Frontend behavior checks passed");
  else console.log("Frontend behavior checks passed");
}).catch(error => {
  if (typeof print === "function") { print(String(error.stack || error)); quit(1); }
  else { console.error(error); process.exit(1); }
});
