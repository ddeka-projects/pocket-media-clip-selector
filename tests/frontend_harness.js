// Small fake DOM/transport for behavior checks; real Safari layout/media are manual QA.
const elements = new Map();
class Element {
  constructor(id) {
    this.id = id; this.hidden = false; this.disabled = false; this.textContent = "";
    this.value = ""; this.children = []; this.listeners = {}; this.attributes = {};
    this.open = false; this.dataset = {};
    const classes = new Set();
    this.classList = {
      toggle(name, force = !classes.has(name)) { if (force) classes.add(name); else classes.delete(name); },
      add(name) { classes.add(name); }, remove(name) { classes.delete(name); }, contains(name) { return classes.has(name); }
    };
  }
  addEventListener(name, action) { (this.listeners[name] ||= []).push(action); }
  dispatchEvent(event) { for (const action of this.listeners[event.type] || []) action(event); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren() { this.children = []; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  removeAttribute(name) { delete this.attributes[name]; }
  get valueAsNumber() { return Number(this.value); }
  showModal() { this.open = true; }
  close() { this.open = false; }
}
function element(id) { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); }
const fakeVideo = element("video");
Object.assign(fakeVideo, { currentTime: 0, duration: 120.5, playbackRate: 1, paused: false, pauseCalls: 0,
  pause() { this.paused = true; this.pauseCalls++; }, play() { this.paused = false; return Promise.resolve(); }, load() {} });
const fakeSkips = [-5, 5].map(value => { const node = new Element("skip"); node.dataset.skip = String(value); return node; });
const fakeRates = [0.25, 0.5, 1, 2, 3].map(value => { const node = new Element("rate"); node.dataset.rate = String(value); return node; });
globalThis.document = Object.assign(element("document"), { hidden: false, body: element("body"), getElementById: element, createElement: (tag) => new Element(tag),
  querySelectorAll: (selector) => ({ "[data-skip]": fakeSkips, "[data-rate]": fakeRates, "[data-skip], [data-rate]": [...fakeSkips, ...fakeRates] }[selector] || []) });
globalThis.window = Object.assign(element("window"), { scrollTo() {} });
let randomCounter = 0;
globalThis.crypto = { getRandomValues: (bytes) => { bytes.fill(0); bytes[0] = ++randomCounter; return bytes; } };
// Record timers without waiting for ordinary request deadlines or toast dismissal.
const timerDelays = []; let intervalCalls = 0;
globalThis.setTimeout = (action, delay) => { timerDelays.push(delay); return timerDelays.length; }; globalThis.clearTimeout = () => {};
globalThis.setInterval = () => { intervalCalls++; return 1; }; globalThis.clearInterval = () => {};
globalThis.AbortController = class { signal = {}; abort() {} };
globalThis.URLSearchParams = class {
  constructor(data) { this.data = data; this.size = Object.keys(data).length; }
  toString() { return Object.entries(this.data).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&"); }
};
let transport;
globalThis.fetch = (...args) => transport(...args);
