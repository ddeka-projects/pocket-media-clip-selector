async function checks(){
 setup("projects");element("project-name").value="Just a name";
 transport=async(path,options)=>{
  equal(path,"/api/projects","project creation endpoint");
  equal(Object.keys(JSON.parse(options.body)).join(","),"name","project creation only asks for a name");
  const created=snapshot([],"Episode 01",null);created.name="Just a name";created.sources=[];created.source_count=0;created.next_source_name="Episode 01";
  return reply(created);
 };
 element("project-form").listeners.submit[0](submit);while(state.busy)await Promise.resolve();
 equal(state.view,"sources","created project opens Sources immediately");
 equal(element("source-summary").textContent,"0 sources · 0 bookmarks","project header shows content counts");
 equal(element("new-source").disabled,false,"source creation needs no setup step");
 openSourceDialog();equal(element("source-name").value,"Episode 01","new project retains episode defaults");element("source-dialog").close();
 setup("quick");
 remember();const saved=JSON.parse(stored.get(preferenceKey));
 equal(saved.project,state.project,"last project is remembered");equal(saved.source,state.source,"last source is remembered");
 equal(Object.keys(saved).sort().join(","),"project,source","controller credentials are never persisted");
 equal(readPreference().source,state.source,"preference survives a page launch");
 stored.set(preferenceKey,"invalid json");equal(readPreference(),null,"damaged preference does not block startup");
 remember();
 const draftCount=state.drafts.size; let lifecycleCalls=0;transport=async()=>{lifecycleCalls++;throw new Error("should not request");};
 document.hidden=true;document.dispatchEvent({type:"visibilitychange"});
 for(const type of ["pagehide","offline","online","pageshow"])window.dispatchEvent({type});
 equal(lifecycleCalls,0,"lifecycle events do not send ownership requests");equal(state.owned,true,"ownership persists");
 equal(state.drafts.size,draftCount,"lifecycle does not clear or mutate a draft");

 setup("quick");state.meta=snapshot([],"Episode 01",null);render();input("1742");
 let calls=0,body,finish;transport=async(path,options)=>{calls++;body=JSON.parse(options.body);equal(path.startsWith("/api/bookmarks?"),true,"single bookmark endpoint");equal(body.time,1062,"Quick Log parses compact digits");equal(Object.keys(body).sort().join(","),"id,time","no range is sent");return await new Promise(resolve=>{finish=()=>resolve(reply(snapshot([{id:body.id,time:body.time}],"Episode 01",null)));});};
 const pending=saveQuick(submit);await saveQuick(submit);equal(calls,1,"double submit never sends a second write");
 equal(element("quick-time").value,"1742","input stays until confirmed");equal(state.busy,true,"save is pending");
 finish();await pending;
 equal(element("quick-time").value,"","confirmed save clears entry");equal(state.source,"Episode 01","save keeps same source");
 assert(element("quick-time").focusCalls>0,"confirmed save returns focus");equal(currentSource().bookmarks[0].time,1062,"bookmark installed without media");

 input("1768");calls=0;transport=async()=>{calls++;return reply({});};await saveQuick(submit);
 equal(calls,0,"invalid seconds are not sent");equal(element("quick-time").value,"1768","invalid input remains visible");assert(element("quick-message").textContent.includes("Seconds"),"invalid seconds explained");

 input("11432");let attemptedId;transport=async(path,options)=>{attemptedId=JSON.parse(options.body).id;throw new Error("offline");};
 await saveQuick(submit);equal(element("quick-time").value,"11432","network failure keeps entry");equal(state.owned,true,"network failure keeps authority");
 assert(element("quick-message").textContent.includes("Cannot confirm"),"uncertain save is honest");
 transport=async(path,options)=>{const retry=JSON.parse(options.body);equal(retry.id,attemptedId,"explicit retry reuses identity");return reply(snapshot([{id:retry.id,time:retry.time}],"Episode 01",null));};
 await saveQuick(submit);equal(currentSource().bookmarks.length,1,"retry confirmed once");equal(element("quick-time").value,"","retry clears only after acknowledgement");

 input("332");transport=async(path,options)=>{const captured=JSON.parse(options.body);input("1742");return reply(snapshot([{id:captured.id,time:captured.time}],"Episode 01",null));};
 await saveQuick(submit);equal(element("quick-time").value,"1742","typing next entry during a save is preserved");

 setup();
 for(const rate of fakeRates){rate.listeners.click[0]();equal(fakeVideo.playbackRate,Number(rate.dataset.rate),"speed changes");equal(rate.getAttribute("aria-pressed"),"true","accepted rate selected");equal(element("speed-notice").hidden,true,"no routine speed warning");}
 equal(fakeVideo.pauseCalls,0,"speed changes do not pause");
 fakeVideo.playbackRate=1.5;syncRate();equal(element("actual-speed").textContent,"1.5× actual","native rate is truthful");
 Object.defineProperty(fakeVideo,"playbackRate",{configurable:true,get(){return 1;},set(){throw new Error("unsupported");}});
 fakeRates[4].listeners.click[0]();equal(fakeRates[2].getAttribute("aria-pressed"),"true","rejected rate keeps real selected speed");equal(element("speed-notice").hidden,false,"real assignment failure is explained");
 Object.defineProperty(fakeVideo,"playbackRate",{configurable:true,writable:true,value:1});
 fakeSkips[0].listeners.click[0]();equal(fakeVideo.currentTime,45.125,"minus five keeps precision");fakeSkips[1].listeners.click[0]();equal(fakeVideo.currentTime,50.125,"plus five keeps precision");
 let capturedTime;transport=async(path,options)=>{const row=JSON.parse(options.body);capturedTime=row.time;fakeVideo.currentTime=72;return reply(snapshot([row]));};
 await saveWatch();equal(capturedTime,50.125,"watch samples at tap before network work");equal(currentSource().bookmarks[0].time,50.125,"fractional timestamp is retained");equal(fakeVideo.pauseCalls,0,"bookmark does not pause");
 openWatch(45.125);equal(fakeVideo.currentTime,45.125,"bookmark jumps to marked moment");fakeVideo.currentTime=100;updateTime();equal(fakeVideo.paused,false,"no automatic range stop remains");
 transport=async()=>{throw new Error("offline");};await saveWatch();const watchId=state.watchPending.id;
 equal(state.watchPending.time,100,"unconfirmed watch moment retained");equal(fakeVideo.paused,false,"failed bookmark keeps playing");assert(element("watch-save-message").textContent.includes("1:40"),"failed watch time visible");
 fakeVideo.currentTime=110;transport=async(path,options)=>{const row=JSON.parse(options.body);equal(row.id,watchId,"watch retry is idempotent");equal(row.time,100,"watch retry saves original moment");return reply(snapshot([row]));};
 await saveWatch(true);equal(state.watchPending,null,"confirmed watch retry clears pending");

 setup("bookmarks");const original={id:"fractional-bookmark-id",time:50.875};state.meta=snapshot([original],"Episode 01",null);render();editBookmark(original);
 equal(element("edit-time").value,"050","edit uses friendly compact time");
 transport=async(path,options)=>{equal(JSON.parse(options.body).time,50.875,"unchanged edit preserves local fractional precision");return reply(snapshot([original],"Episode 01",null));};
 await element("edit-form").listeners.submit[0](submit); // Handler dispatches an async mutation.
 while(state.busy)await Promise.resolve();equal(element("edit-dialog").open,false,"edit works without a local MP4");

 setup("quick");input("1742");openSourceDialog(currentSource());element("source-name").value="Movie";
 transport=async(path,options)=>{const changed=JSON.parse(options.body);equal(changed.name,"Movie","rename sends visible name");equal(changed.media_file,"scene.mp4","rename preserves association");return reply(snapshot([],"Movie"));};
 element("source-form").listeners.submit[0](submit);while(state.busy)await Promise.resolve();
 equal(state.source,"Movie","renamed source selected");equal(element("quick-time").value,"1742","rename carries unfinished draft");
 equal(draftFor(state.project,"Episode 01").raw,"","reusing an old source name does not inherit the renamed draft");
 openSourceDialog(currentSource());element("source-name").value="Other spelling";
 transport=async()=>{throw new Error("offline");};element("source-form").listeners.submit[0](submit);while(state.busy)await Promise.resolve();
 equal(element("source-dialog").open,true,"failed source write keeps dialog");equal(element("source-name").value,"Other spelling","failed source write keeps entry");element("source-dialog").close();
 remember();confirmDelete("source");
 transport=async()=>{const result=snapshot();result.sources=[];result.source_count=0;return reply(result);};
 element("confirm-form").listeners.submit[0](submit);while(state.busy)await Promise.resolve();
 equal(state.remembered,null,"removed source is not offered as a remembered shortcut");equal(state.view,"sources","removed source returns to Sources");

 setup("quick");input("1742");transport=async()=>reply({error:{code:"controller_transferred",message:"Editor control was transferred to another page"}},false);
 await saveQuick(submit);equal(state.owned,false,"stale save loses write authority");equal(element("quick-time").value,"1742","takeover rejection preserves entry");equal(element("quick-save").disabled,true,"stale editor cannot save");equal(element("workspace").hidden,true,"stale page is gated");equal(element("gate-take-control").hidden,false,"explicit takeover is offered");
 const oldPage=state.page;transport=async(path,options)=>{
  if(path==="/api/controller/takeover"){equal(JSON.parse(options.body).page_id,oldPage,"takeover preserves page identity");return reply({token:"new-token"});}
  if(path==="/api/projects")return reply({projects:[{name:state.project}]});
  return reply(snapshot([],"Episode 01",null));
 };
 await acquireControl(true);equal(state.owned,true,"explicit takeover acquires");equal(state.token,"new-token","new token kept in memory");equal(element("quick-time").value,"1742","explicit takeover retains unsaved draft");

 setup();const position=fakeVideo.currentTime;
 transport=async()=>{throw new Error("offline");};await exitEditor();equal(state.owned,true,"unconfirmed exit keeps state");equal(fakeVideo.paused,false,"unconfirmed exit does not pause");
 transport=async(path,options)=>{equal(path,"/api/controller/release","exit explicitly releases");equal(JSON.parse(options.body).token,state.token,"release uses opaque token");return reply({released:true});};
 await exitEditor();equal(state.owned,false,"confirmed exit releases");equal(fakeVideo.paused,true,"confirmed exit pauses");equal(element("gate-title").textContent,"Editor exited","entry gate visible");
 transport=async path=>path==="/api/controller/claim"?reply({token:"reentered-token"}):path==="/api/projects"?reply({projects:[{name:state.project}]}):reply(snapshot());
 await acquireControl();equal(fakeVideo.currentTime,position,"reentry retains playback position");equal(state.view,"player","reentry keeps watch view");

 setup("projects");state.project=state.source=state.meta=null;state.owned=false;state.remembered={project:"A show – 日本語",source:"Episode 01"};
 transport=async path=>path==="/api/controller/claim"?reply({token:"launch-token"}):path==="/api/projects"?reply({projects:[{name:"A show – 日本語"}]}):reply(snapshot([],"Episode 01",null));
 await acquireControl();equal(state.view,"quick","new launch restores Quick Log");equal(state.source,"Episode 01","new launch restores source");

 setup();const oldEpoch=state.epoch;let resolveLate;
 transport=async()=>new Promise(resolve=>{resolveLate=resolve;});const late=request("/api/project");state.epoch++;
 resolveLate(reply(snapshot()));let suppressed=false;try{await late;}catch(error){suppressed=error.code==="session_changed";}
 equal(suppressed,true,"late responses from old ownership are ignored");assert(state.epoch>oldEpoch,"ownership epoch advanced");
 equal(intervalCalls,0,"no background polling added");assert(timerDelays.every(delay=>[12000,2600,8000].includes(delay)),"only request deadlines and toast timers");
 for(const entry of storageWrites){equal(Object.keys(JSON.parse(entry.value)).sort().join(","),"project,source","storage never contains ownership authority");}
}
checks().then(()=>{if(typeof print==="function")print("Frontend behavior checks passed");else console.log("Frontend behavior checks passed");},error=>{if(typeof print==="function"){print(error.stack);throw error;}else{console.error(error);process.exitCode=1;}});
