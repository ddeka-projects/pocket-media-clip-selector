// Small fake DOM/transport for behavior checks; real Safari layout/media are manual QA.
const elements = new Map();
class Element {
  constructor(id) {
    this.id = id; this.hidden = false; this.disabled = false; this.textContent = "";
    this.value = ""; this.children = []; this.listeners = {}; this.attributes = {};
    this.options = []; this.open = false; this.dataset = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(name, action) { (this.listeners[name] ||= []).push(action); }
  append(...nodes) { this.children.push(...nodes); if (this.id === "speed") this.options.push(...nodes); }
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
element("speed").options = [0.25, 0.5, 1, 2, 3].map(value => ({ value: String(value) }));
const fakeSkips = [-15, -5, 5, 15].map(value => { const node = new Element("skip"); node.dataset.skip = String(value); return node; });
globalThis.document = { hidden: false, getElementById: element, createElement: (tag) => new Element(tag), addEventListener() {},
  querySelectorAll: (selector) => selector === "[data-skip]" ? fakeSkips : [] };
globalThis.window = { addEventListener() {}, scrollTo() {} };
let randomCounter = 0;
globalThis.crypto = { getRandomValues: (bytes) => { bytes.fill(0); bytes[0] = ++randomCounter; return bytes; } };
// Keep scheduled heartbeats/retries out of unit tests.
globalThis.setTimeout = () => 1; globalThis.clearTimeout = () => {};
globalThis.setInterval = () => 1; globalThis.clearInterval = () => {};
globalThis.AbortController = class { signal = {}; abort() {} };
globalThis.URLSearchParams = class {
  constructor(data) { this.data = data; this.size = Object.keys(data).length; }
  toString() { return Object.entries(this.data).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&"); }
};
let transport;
globalThis.fetch = (...args) => transport(...args);
