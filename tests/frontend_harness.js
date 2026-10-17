// Fake DOM and transport for application behavior; WebKit covers layout separately.
const elements = new Map();
class Element {
  constructor(id) {
    this.id=id; this.hidden=false; this.disabled=false; this.textContent=""; this.value="";
    this.children=[]; this.listeners={}; this.attributes={}; this.open=false; this.dataset={};
    this.parentElement={hidden:false}; this.focusCalls=0; this.selectCalls=0;
    const classes=new Set();
    this.classList={toggle(name,force=!classes.has(name)){if(force)classes.add(name);else classes.delete(name);},add(name){classes.add(name);},remove(name){classes.delete(name);},contains(name){return classes.has(name);}};
  }
  addEventListener(name,action){(this.listeners[name] ||= []).push(action);}
  dispatchEvent(event){for(const action of this.listeners[event.type] || []) action(event);}
  append(...nodes){for(const node of nodes)node.parentElement=this;this.children.push(...nodes);}
  replaceChildren(){this.children=[];}
  setAttribute(name,value){this.attributes[name]=value;}
  getAttribute(name){return this.attributes[name];}
  removeAttribute(name){delete this.attributes[name];}
  focus(){this.focusCalls++;document.activeElement=this;}
  select(){this.selectCalls++;}
  showModal(){this.open=true;}
  close(){this.open=false;}
}
function element(id){if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);}
const fakeVideo=element("video");
Object.assign(fakeVideo,{currentTime:0,duration:120.5,playbackRate:1,paused:false,pauseCalls:0,
 pause(){this.paused=true;this.pauseCalls++;},play(){this.paused=false;return Promise.resolve();},load(){}});
const fakeSkips=[-5,5].map(value=>{const e=new Element("skip");e.dataset.skip=String(value);return e;});
const fakeRates=[.25,.5,1,2,3].map(value=>{const e=new Element("rate");e.dataset.rate=String(value);return e;});
globalThis.document=Object.assign(element("document"),{hidden:false,body:element("body"),getElementById:element,createElement:tag=>new Element(tag),
 querySelectorAll:selector=>({"[data-skip]":fakeSkips,"[data-rate]":fakeRates,"[data-skip], [data-rate]":[...fakeSkips,...fakeRates]}[selector] || [])});
globalThis.window=Object.assign(element("window"),{scrollTo(){}});
let randomCounter=0;
globalThis.crypto={getRandomValues:bytes=>{bytes.fill(0);bytes[0]=++randomCounter;return bytes;}};
const stored=new Map(), storageWrites=[];
globalThis.localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>{stored.set(key,value);storageWrites.push({key,value});},removeItem:key=>stored.delete(key)};
const timerDelays=[];let intervalCalls=0;
globalThis.setTimeout=(action,delay)=>{timerDelays.push(delay);return timerDelays.length;};globalThis.clearTimeout=()=>{};
globalThis.setInterval=()=>{intervalCalls++;return 1;};globalThis.clearInterval=()=>{};
globalThis.AbortController=class{signal={};abort(){}};
globalThis.URLSearchParams=class{constructor(data){this.data=data;}toString(){return Object.entries(this.data).map(([k,v])=>`${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");}};
let transport;
globalThis.fetch=(...args)=>transport(...args);
function assert(condition,message){if(!condition)throw new Error(message);}
function equal(actual,expected,message){assert(actual===expected,`${message}: ${actual} !== ${expected}`);}
function reply(payload,ok=true){return {ok,json:async()=>payload};}
function snapshot(bookmarks=[],source="Episode 01",file="scene.mp4"){
 return {name:"A show – 日本語",revision:"revision-next",next_source_name:"Episode 02",media:file?[{name:file}]:[],source_count:1,bookmark_count:bookmarks.length,
  sources:[{name:source,media_file:file,available:Boolean(file),next_episode_name:"Episode 02",bookmarks}]};
}
function setup(view="player"){
 Object.assign(state,{project:"A show – 日本語",source:"Episode 01",meta:snapshot(),projects:[{name:"A show – 日本語"}],
  owned:true,token:"live-token",ready:true,busy:false,controlBusy:false,view,watchPending:null,pendingSeek:null,loaded:{project:"A show – 日本語",file:"scene.mp4"},drafts:new Map()});
 Object.assign(fakeVideo,{paused:false,pauseCalls:0,currentTime:50.125,duration:120.5,playbackRate:1});
 fakeVideo.setAttribute("src","/media");element("workspace").hidden=false;element("gate").hidden=true;element("control-notice").hidden=true;element("toast").hidden=true;
 showView(view);if(view==="player")fakeVideo.paused=false;fakeVideo.pauseCalls=0;
}
const submit={preventDefault(){}};
function input(value){element("quick-time").value=value;element("quick-time").dispatchEvent({type:"input"});}
