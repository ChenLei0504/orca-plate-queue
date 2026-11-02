/* DOM flow tests. This fake bridge never loads a networking library. */
const {JSDOM}=require('./.ui-test-tools/node_modules/jsdom');
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('plugin_page.html','utf8').replace('<script src="plugin_page.js"></script>','');
const js=fs.readFileSync('plugin_page.js','utf8');
const clone=v=>JSON.parse(JSON.stringify(v));
const png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7xkAAAAASUVORK5CYII=';
function fixture(){
 const settings={device_id:'fixture-a1',source:'ams',mapping:{},options:{bed_leveling:true,flow_calibration:false,timelapse:false}};
 const jobs=[1,2].map(i=>({id:'job'+i,name:'中部'+i+'.3mf',status:'等待',plate:String(i+4),duration_s:i===1?14520:10920,weight_g:67,
  object_count:2,objects:[{id:'1419',name:'零件一'},{id:'1420',name:'零件二'}],label_markers:true,printer:'N2S',nozzle:'.4',sha256:'hash'+i,
  filaments:[{id:'9',type:'PETG',color:'#EBE6E6',profile_id:'GFG99',nozzle:'.40'}],settings:clone(settings)}));
 const data={schema:3,jobs,device_id:'fixture-a1',previews:{hash1:png,hash2:png},running:false,phase:'paused',active:null,dirty_plate:false,auto_after_swap:false,drafts:[]};
 return {type:'state',success:true,data,setup:{job1:{configured:false,ready:false},job2:{configured:false,ready:false}},
  swap_settings:{path:'private/hash.3mf',source_path:'E:/kit/default.3mf',name:'默认机械换盘.3mf',nozzle:.4,motion_only:true,enabled:true,validated:true,settings:clone(settings)},
  swap_setup:{ready:true},swap_plan:[{after_id:'job1',before_id:'job2',file:'private/hash.3mf',nozzle:.4}],
  connection:{available:true,can_submit:true,commands:[],devices:[{id:'fixture-a1',name:'A1',model:'N2S',nozzle:.4,online:true,cloud_connected:true,age_ms:0,
   supported_options:['bed_leveling','flow_calibration','timelapse'],telemetry:{gcode_state:'IDLE',nozzle_temper:20,bed_temper:21},filament_at_toolhead:0,
   slots:[{id:'ams/0/tray/0',label:'AMS 1 / 1',type:'',kind:'ams',present:false,color:''},{id:'external',label:'外挂耗材',kind:'external',type:'PETG',present:false,color:'#BDBEBDFF'}]}]},messages:[]};
}
async function tick(){await new Promise(r=>setImmediate(r))}
function launch(initial=fixture()){
 let state=clone(initial),listener,requests=[],fileClicks=0,preflightError='',commitError='',upload=null,deferPreflight=false,deferred=[],deferPreview=false,deferredPreview=[];
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'https://queue.invalid/'}),w=dom.window;
 w.HTMLElement.prototype.scrollIntoView=function(){};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};
 w.document.getElementById('fileInput').click=()=>{fileClicks++};
 const reply=r=>listener(r);
 const handle=req=>{
  requests.push(clone(req));
  if(req.action==='object_preview'){if(deferPreview){deferredPreview.push(req);return}reply({success:true,action:req.action,request_id:req.request_id,queue_id:state.queue_id??state.data.device_id,job_id:req.id,preview:clone(state.object_preview||objectPreviewFixture(state.data.jobs.find(j=>j.id===req.id)?.objects||[]))});return}
  if(req.action==='preflight'){
   if(deferPreflight){deferred.push(req);return}
   if(preflightError){reply({type:'error',success:false,request_id:req.request_id,note:preflightError});return}
  }
  if(req.action==='save_settings'){
   const ids=[req.id,...req.apply_to||[]];for(const id of ids){state.data.jobs.find(j=>j.id===id).settings=clone(req.settings);state.setup[id]={configured:true,ready:false}}
  }
  if(req.action==='remove'){
   state.data.jobs=state.data.jobs.filter(j=>j.id!==req.id);delete state.setup[req.id];state.swap_plan=state.swap_plan.filter(s=>s.after_id!==req.id&&s.before_id!==req.id);
  }
  if(req.action==='commit_import'&&commitError){reply({success:false,request_id:req.request_id,note:commitError});return}
  const stage=(name,copies)=>{const asset=clone(fixture().data.jobs[0]);asset.id='draft'+requests.length;asset.name=name;asset.copies=copies;delete asset.status;state.data.drafts||=[];state.data.drafts.push(asset)};
  if(req.action==='add')stage('路径导入.3mf',req.copies||1);
  if(req.action==='upload_begin'){upload={name:req.name,copies:req.copies};reply({success:true,request_id:req.request_id,upload:{token:'local-upload',chunk_size:192*1024}});return}
  if(req.action==='upload_end')stage(upload.name,upload.copies);
  if(req.action==='commit_import'){const ids=[req.id,...req.apply_to||[]];for(const id of ids){const draft=state.data.drafts.find(d=>d.id===id);for(let i=0;i<(id===req.id?(req.copies??draft.copies):draft.copies);i++){const row=clone(draft);row.id=id+'-job'+i;row.status='等待';row.settings=clone(req.settings);state.data.jobs.push(row);state.setup[row.id]={configured:true,ready:false}}}state.data.drafts=state.data.drafts.filter(d=>!ids.includes(d.id))}
  if(req.action==='discard_import')state.data.drafts=state.data.drafts.filter(d=>d.id!==req.id);
  if(req.action==='select_queue'&&state.queue_states){const view=state.queue_states[req.device_id];state={...state,...clone(view),queue_id:req.device_id}}
  const out=clone(state);Object.assign(out,{action:req.action,request_id:req.request_id,success:true,note:''});reply(out);
 };
 w.orca={onMessage:f=>{listener=f},postMessage:req=>handle(req)};w.eval(js);
 return {w,dom,requests,el:id=>w.document.getElementById(id),state:()=>state,set:v=>{state=clone(v);reply(state)},
  deliver:v=>reply(clone(v)),
  get fileClicks(){return fileClicks},set deferPreview(v){deferPreview=v},flushPreview(){const req=deferredPreview.shift();if(req)reply({success:true,request_id:req.request_id,queue_id:state.queue_id??state.data.device_id,job_id:req.id,preview:clone(state.object_preview||objectPreviewFixture(state.data.jobs.find(j=>j.id===req.id)?.objects||[]))})},set preflightError(v){preflightError=v},set commitError(v){commitError=v},set deferPreflight(v){deferPreflight=v},
  flushPreflight(){const req=deferred.shift();if(req){const out=clone(state);Object.assign(out,{action:req.action,request_id:req.request_id});reply(out)}},
  close:()=>w.close()};
}
const tests=[];function test(name,fn){tests.push([name,fn])}

function multiFixture(){const s=fixture(),a=clone(s.data),b=clone(s.data);a.running=true;a.phase='monitoring';a.jobs[0].status='打印中';a.active={kind:'model',job_id:'job1',identity:{subtask_id:'a'},tag:'oq_a'};b.device_id='fixture-p1';b.plate_mode='manual';b.jobs=b.jobs.map(j=>({...j,id:'p1-'+j.id,printer:'C12',settings:{...j.settings,device_id:'fixture-p1',mapping:{'9':'ams/0/tray/0'}}}));const p1=clone(s.connection.devices[0]);p1.id='fixture-p1';p1.name='P1S';p1.model='C12';p1.supported_options=['bed_leveling','timelapse'];s.connection.devices.push(p1);s.queue_id='fixture-a1';s.data=a;s.fleet=[{id:'fixture-a1',name:'A1',model:'N2S',online:true,running:true,active:true,pending:1,completed:0},{id:'fixture-p1',name:'P1S',model:'C12',online:true,running:false,pending:2,completed:0}];s.queue_states={'fixture-a1':{data:a,setup:s.setup,swap_settings:s.swap_settings,swap_setup:s.swap_setup},'fixture-p1':{data:b,setup:Object.fromEntries(b.jobs.map(j=>[j.id,{configured:true,ready:true}])),swap_settings:{enabled:false,validated:false,path:'',settings:{device_id:'fixture-p1',source:'ams',mapping:{},options:{bed_leveling:true,flow_calibration:false,timelapse:false}}},swap_setup:{ready:false}}};return s}
test('multiple printers are visible and switching views does not stop a running queue',async()=>{
 const t=launch(multiFixture());try{assert.equal(t.el('fleetQueues').querySelectorAll('button').length,2);assert.ok([...t.el('fleetQueues').querySelectorAll('button')].every(b=>!b.disabled));[...t.el('fleetQueues').querySelectorAll('button')].find(b=>b.textContent.includes('P1S')).click();await tick();assert.equal(t.state().data.device_id,'fixture-p1');assert.equal(t.el('quickAdd').disabled,false);assert.equal(t.requests.find(r=>r.action==='select_queue').queue_id,'fixture-a1');assert.equal(t.state().queue_states['fixture-a1'].data.running,true);assert.equal(t.requests.filter(r=>r.action==='stop_queue').length,0);assert.match(t.el('jobs').textContent,/中部1/)}finally{t.close()}
});
test('late replies from an old machine cannot replace the current machine view',async()=>{
 const initial=multiFixture(),old=clone(initial),t=launch(initial);try{[...t.el('fleetQueues').querySelectorAll('button')].find(b=>b.textContent.includes('P1S')).click();await tick();t.deliver(old);assert.equal(t.el('queueName').textContent,'P1S 的队列');assert.ok(t.el('jobs').querySelector('article').dataset.id.startsWith('p1-'));assert.equal(t.el('stopQueue').hidden,true)}finally{t.close()}
});
test('P1 queues use manual plate changes without enabling an automatic swap file',async()=>{
 const t=launch(multiFixture());try{[...t.el('fleetQueues').querySelectorAll('button')].find(b=>b.textContent.includes('P1S')).click();await tick();assert.match(t.el('swapFileName').textContent,/更换或清空/);assert.equal(t.el('plateHandlingStep').textContent,'手动换板并确认');assert.match(t.el('readinessList').textContent,/手动换板模式已设置/);t.w.openStart('start');assert.match(t.el('bedClearGroup').textContent,/打印区域已清空/);t.el('startDialog').close();assert.match(t.el('startQueue').textContent,/检查并开始/);t.el('openSwap').click();assert.equal(t.el('plateMode').value,'manual');assert.equal(t.el('plateMode').querySelector('option[value=automatic]').disabled,true);assert.equal(t.el('swapFileFields').hidden,true);assert.equal(t.el('defaultSwap').disabled,true);t.el('saveSwap').click();await tick();assert.equal(t.requests.find(r=>r.action==='save_swap').plate_mode,'manual')}finally{t.close()}
});
test('the current device list only offers A1 and P1S queues',async()=>{
 for(const model of ['N1','N9','C11','BL-P001']){const s=fixture();s.connection.devices[0].model=model;const t=launch(s);try{assert.equal(t.el('fleetQueues').querySelectorAll('button').length,0);assert.equal(t.el('quickAdd').disabled,true)}finally{t.close()}}
});
test('switching to another printer closes stale dialogs and keeps imports scoped',async()=>{
 const s=multiFixture();s.data.running=false;s.data.phase='paused';s.data.active=null;s.data.jobs[0].status='等待';s.queue_states['fixture-a1'].data=clone(s.data);const t=launch(s);try{t.el('startQueue').click();assert.equal(t.el('settingsDialog').open,true);t.w.selectQueue('fixture-p1');await tick();assert.equal(t.el('settingsDialog').open,false);assert.equal(t.el('queueName').textContent,'P1S 的队列');assert.equal(t.requests.filter(r=>r.action==='save_settings').length,0)}finally{t.close()}
});

test('a removed task disappears immediately with counts and transitions',async()=>{
 const t=launch();try{const s=t.state();s.data.jobs.shift();delete s.setup.job1;s.swap_plan=[];t.set(s);assert.equal(t.el('jobs').querySelectorAll('article').length,1);assert.equal(t.el('jobs').querySelector('article').dataset.id,'job2');assert.equal(t.el('pendingCount').textContent,'1');assert.ok(!t.el('jobs').querySelector('.swap-step'));assert.ok(!t.el('jobs').querySelector('.card-menu[open]'))}finally{t.close()}
});
test('task delete is a visible icon and updates cards counts and empty state without refresh',async()=>{
 const t=launch();try{const first=t.el('jobs').firstElementChild,remove=first.querySelector('button.delete-task');assert.ok(remove);assert.equal(remove.closest('details'),null);assert.equal(remove.textContent,'');assert.ok(remove.querySelector('use[href="#i-trash"]'));assert.match(remove.getAttribute('aria-label'),/删除任务/);remove.click();await tick();assert.deepEqual(t.requests.filter(r=>r.action==='remove').map(r=>r.id),['job1']);assert.equal(t.el('jobs').querySelectorAll('article').length,1);assert.equal(t.el('pendingCount').textContent,'1');assert.match(t.el('summary').textContent,/1 盘待打印/);t.el('jobs').querySelector('button.delete-task').click();await tick();assert.equal(t.el('jobs').querySelectorAll('article').length,0);assert.match(t.el('jobs').textContent,/加入这里/);assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.requests.filter(r=>r.action==='refresh').length,1)}finally{t.close()}
});
test('cards have no overflow menu and active tasks have no delete action',async()=>{
 const t=launch();try{assert.equal(t.el('jobs').querySelector('details'),null);assert.equal(t.el('jobs').querySelector('use[href="#i-more"]'),null);const s=t.state();s.data.jobs[0].status='打印中';s.data.active={job_id:'job1',kind:'model',identity:{subtask_id:'task'}};s.data.phase='monitoring';s.data.running=true;t.set(s);assert.equal(t.el('currentJob').firstElementChild.querySelector('.delete-task'),null)}finally{t.close()}
});

function amsFixture(){const s=fixture();s.connection.devices[0].slots=[0,1,2,3].map(i=>({id:'ams/0/tray/'+i,label:'AMS 1 / '+(i+1),type:'PETG',kind:'ams',present:true,color:i===3?'#000000':'#EBE6E6FF'}));s.data.jobs[0].settings.mapping={'9':'ams/0/tray/0'};return s}
function emptyImportFixture(){const s=fixture();s.data.jobs=[];s.setup={};s.swap_plan=[];return s}
test('import dialog can change copies while periodic updates preserve the draft quantity',async()=>{
 const t=launch(emptyImportFixture());try{t.el('path').value='E:/model.3mf';t.el('add').click();await tick();assert.equal(t.el('importCopies').value,'1');t.el('importCopies').value='4';t.el('importCopies').focus();t.set(t.state());assert.equal(t.el('importCopies').value,'4');t.el('savePrintSettings').click();await tick();assert.equal(t.requests.find(r=>r.action==='commit_import').copies,4);assert.equal(t.el('pendingCount').textContent,'4');assert.equal(t.el('jobs').querySelectorAll('article').length,4)}finally{t.close()}
});
test('invalid dialog quantities never submit an import',async()=>{
 const t=launch(emptyImportFixture());try{t.el('path').value='E:/model.3mf';t.el('add').click();await tick();for(const value of ['','0','101','1.5']){t.el('importCopies').value=value;t.el('savePrintSettings').click();await tick();assert.equal(t.requests.filter(r=>r.action==='commit_import').length,0);assert.match(t.el('settingsError').textContent,/1–100/);assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.el('settingsDialog').open,true)}}finally{t.close()}
});
test('path selection opens materials first and only confirmed copies enter the queue',async()=>{
 const t=launch(emptyImportFixture());try{t.el('path').value='E:/model.3mf';t.el('add').click();await tick();assert.equal(t.el('settingsDialog').open,true);assert.match(t.el('settingsTitle').textContent,/配置耗材后加入/);assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.el('jobs').querySelector('article'),null);assert.equal(t.el('savePrintSettings').textContent,'确认加入队列');t.el('importCopies').value='2';t.el('savePrintSettings').click();await tick();assert.equal(t.requests.filter(r=>r.action==='commit_import').length,1);assert.equal(t.el('pendingCount').textContent,'2');assert.equal(t.el('jobs').querySelectorAll('article').length,2);assert.equal(t.el('settingsDialog').open,false);assert.equal(t.requests.filter(r=>r.action==='start').length,0)}finally{t.close()}
});
test('closing import configuration keeps a pending file and cancel never enqueues it',async()=>{
 const t=launch(emptyImportFixture());try{t.el('path').value='E:/model.3mf';t.el('add').click();await tick();t.el('closeSettings').click();assert.equal(t.el('importPending').hidden,false);assert.equal(t.el('pendingCount').textContent,'0');t.el('configureImports').click();assert.equal(t.el('settingsDialog').open,true);t.el('cancelImport').click();await tick();assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.el('importPending').hidden,true);assert.equal(t.requests.filter(r=>r.action==='commit_import').length,0)}finally{t.close()}
});
test('failed material validation keeps the import outside the queue',async()=>{
 const t=launch(emptyImportFixture());try{t.el('path').value='E:/model.3mf';t.el('add').click();await tick();t.commitError='请选择实际耗材槽位';t.el('savePrintSettings').click();await tick();assert.equal(t.el('settingsDialog').open,true);assert.match(t.el('settingsError').textContent,/实际耗材/);assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.state().data.drafts.length,1)}finally{t.close()}
});
test('dragged file transfers locally then opens configuration without a queue card',async()=>{
 const t=launch(emptyImportFixture());try{const raw=new Uint8Array([1,2,3]);await t.w.importFiles([{name:'拖入的盘.3mf',size:3,slice:()=>({arrayBuffer:async()=>raw.buffer})}]);await tick();assert.equal(t.requests.filter(r=>r.action==='upload_end').length,1);assert.equal(t.el('settingsDialog').open,true);assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.state().data.drafts[0].name,'拖入的盘.3mf');assert.equal(t.requests.filter(r=>r.action==='commit_import').length,0)}finally{t.close()}
});
test('matching imported files may be configured together before any card appears',async()=>{
 const s=emptyImportFixture();s.data.drafts=fixture().data.jobs.map((j,i)=>({...j,id:'import'+i,copies:i+1}));const t=launch(s);try{await tick();assert.equal(t.el('pendingCount').textContent,'0');assert.equal(t.el('applyMatchingLabel').hidden,false);t.el('applyMatching').checked=true;t.el('savePrintSettings').click();await tick();assert.equal(t.el('pendingCount').textContent,'3');assert.deepEqual(t.requests.find(r=>r.action==='commit_import').apply_to,['import1']);assert.equal(t.state().data.drafts.length,0)}finally{t.close()}
});
test('explicit backup selection is opt in and preserves multiple selected slots',async()=>{
 const t=launch(amsFixture());try{t.el('startQueue').click();assert.equal(t.el('settingsDialog').open,true);let inputs=[...t.el('materialMappings').querySelectorAll('[data-backup-slot]')];assert.equal(inputs.length,3);assert.ok(inputs.every(i=>!i.checked));assert.equal(inputs[2].disabled,true);
 inputs[0].click();inputs=[...t.el('materialMappings').querySelectorAll('[data-backup-slot]')];assert.equal(inputs[0].checked,true);assert.equal(inputs[1].disabled,false);inputs[1].click();t.el('savePrintSettings').click();await tick();const req=t.requests.find(r=>r.action==='save_settings');assert.deepEqual(req.settings.refill['9'].slots,['ams/0/tray/1','ams/0/tray/2']);assert.equal(t.requests.filter(r=>r.action==='start').length,0);
 }finally{t.close()}
});
test('switching supply clears backup groups and changing primary requires reselection',async()=>{
 const t=launch(amsFixture());try{t.el('startQueue').click();t.el('materialMappings').querySelector('[data-backup-slot]').click();t.el('materialMappings').querySelector('[data-material-slot="ams/0/tray/2"]').click();assert.ok([...t.el('materialMappings').querySelectorAll('[data-backup-slot]')].every(i=>!i.checked));t.el('materialMappings').querySelector('[data-backup-slot]').click();t.el('materialSource').value='external';t.el('materialSource').dispatchEvent(new t.w.Event('change'));assert.equal(t.el('materialMappings').querySelector('[data-backup-slot]'),null);t.el('savePrintSettings').click();await tick();assert.deepEqual(t.requests.find(r=>r.action==='save_settings').settings.refill,{});
 }finally{t.close()}
});
test('fallback preview shows resolved slot while saved primary remains unchanged',async()=>{
 const s=amsFixture();s.data.jobs[0].settings.refill={'9':{slots:['ams/0/tray/1'],type:'PETG',color:'EBE6E6FF'}};s.connection.devices[0].slots[0].present=false;s.setup.job1={configured:true,ready:true,resolved_mapping:{'9':'ams/0/tray/1'}};const t=launch(s);try{assert.match(t.el('jobs').firstElementChild.textContent,/预计使用备用槽.*AMS 1 \/ 2/);assert.equal(t.state().data.jobs[0].settings.mapping['9'],'ams/0/tray/0')}finally{t.close()}
});
test('empty queue guides to file selection without submission',async()=>{
 const s=fixture();s.data.jobs=[];s.data.previews={};s.setup={};s.swap_plan=[];const t=launch(s);try{assert.match(t.el('startQueue').textContent,/加入任务/);t.el('startQueue').click();assert.equal(t.fileClicks,1);assert.equal(t.requests.filter(r=>r.action==='start').length,0)}finally{t.close()}
});
test('periodic snapshots preserve card focus and selection',async()=>{
 const t=launch();try{const card=t.el('jobs').firstElementChild;const settings=card.querySelector('.primary');settings.focus();const s=t.state();s.connection.devices[0].telemetry.nozzle_temper=21;t.set(s);assert.equal(t.el('jobs').firstElementChild,card);assert.equal(t.w.document.activeElement,settings)}finally{t.close()}
});
test('printer navigation preserves focus when temperatures update',async()=>{
 const t=launch(multiFixture());try{const card=t.el('fleetQueues').firstElementChild;card.focus();const s=t.state();s.connection.devices[0].telemetry.nozzle_temper=24;t.set(s);assert.equal(t.el('fleetQueues').firstElementChild,card);assert.equal(t.w.document.activeElement,card)}finally{t.close()}
});
test('one file picker action opens it exactly once',async()=>{
 const t=launch();try{t.el('dropZone').click();assert.equal(t.fileClicks,1);t.el('dropZone').dispatchEvent(new t.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));assert.equal(t.fileClicks,2)}finally{t.close()}
});
test('suggested external mapping stays unsaved until Save, with explicit bulk targets',async()=>{
 const t=launch();try{t.el('startQueue').click();assert.equal(t.el('settingsDialog').open,true);assert.equal(t.el('materialSource').value,'external');
  assert.equal(t.el('materialMappings').querySelector('[data-material-slot=external]').getAttribute('aria-pressed'),'true');assert.equal(t.el('externalReadyLabel').hidden,true);assert.equal(t.el('applyMatchingLabel').hidden,false);
  assert.equal(t.requests.filter(r=>r.action==='save_settings').length,0);t.el('applyMatching').checked=true;t.el('savePrintSettings').click();await tick();
  const request=t.requests.find(r=>r.action==='save_settings');assert.equal(request.settings.source,'external');assert.deepEqual(request.apply_to,['job2']);
  assert.equal(t.el('settingsDialog').open,false);assert.match(t.el('startQueue').textContent,/检查并开始/);
  assert.equal(t.requests.filter(r=>r.action==='start').length,0);
 }finally{t.close()}
});
test('bulk selection excludes different filament colors and already started jobs',async()=>{
 const s=fixture();s.data.jobs[1].filaments[0].color='#FF0000';const t=launch(s);try{t.el('startQueue').click();assert.equal(t.el('applyMatchingLabel').hidden,true)}finally{t.close()}
});
test('failed physical readiness prevents start even after plate acknowledgement',async()=>{
 const s=fixture();for(const report of Object.values(s.setup))Object.assign(report,{configured:true,ready:false});const t=launch(s);
 try{t.preflightError='喷头无料';t.el('startQueue').click();await tick();assert.equal(t.el('startDialog').open,true);t.el('bedClear').checked=true;t.el('bedClear').dispatchEvent(new t.w.Event('change'));assert.equal(t.el('confirmStart').disabled,true);t.el('confirmStart').click();assert.equal(t.requests.filter(r=>r.action==='start').length,0);assert.match(t.el('startError').textContent,/无料/)}finally{t.close()}
});
test('preflight and acknowledgement are both required before starting',async()=>{
 const s=fixture();for(const report of Object.values(s.setup))Object.assign(report,{configured:true,ready:true});s.connection.devices[0].slots[1].present=true;const t=launch(s);
 try{t.el('startQueue').click();await tick();assert.equal(t.el('confirmStart').disabled,true);t.el('bedClear').checked=true;t.el('bedClear').dispatchEvent(new t.w.Event('change'));assert.equal(t.el('confirmStart').disabled,false);t.el('confirmStart').click();await tick();const calls=t.requests.filter(r=>['preflight','start'].includes(r.action));assert.deepEqual(calls.map(r=>r.action),['preflight','start']);assert.equal(calls[0].for_start,true);assert.equal(calls[1].bed_clear,true)}finally{t.close()}
});
test('late preflight result cannot approve a newly reopened dialog',async()=>{
 const s=fixture();for(const report of Object.values(s.setup))Object.assign(report,{configured:true,ready:true});const t=launch(s);
 try{t.deferPreflight=true;t.el('startQueue').click();t.el('closeStart').click();t.el('startQueue').click();t.el('bedClear').checked=true;t.el('bedClear').dispatchEvent(new t.w.Event('change'));t.flushPreflight();await tick();assert.equal(t.el('confirmStart').disabled,true);t.flushPreflight();await tick();assert.equal(t.el('confirmStart').disabled,false)}finally{t.close()}
});
test('swap draft is cancelled without changing persisted settings',async()=>{
 const t=launch();try{t.el('openSwap').click();assert.equal(t.el('swapPath').value,'E:/kit/default.3mf');t.el('swapAuto').checked=true;t.el('swapAuto').dispatchEvent(new t.w.Event('input'));t.el('cancelSwap').click();assert.equal(t.requests.filter(r=>['save_swap','swap_mode'].includes(r.action)).length,0);t.el('openSwap').click();assert.equal(t.el('swapAuto').checked,false)}finally{t.close()}
});
test('printing card exposes one suitable pause action and separate ending intent',async()=>{
 const s=fixture();s.data.running=true;s.data.phase='monitoring';s.data.jobs[0].status='打印中';s.data.active={job_id:'job1',kind:'model',identity:{subtask_id:'task'},tag:'oq_test'};s.connection.devices[0].telemetry.gcode_state='RUNNING';const t=launch(s);
 try{const card=t.el('currentJob').firstElementChild;assert.match(card.textContent,/暂停打印/);assert.ok(!card.textContent.includes('继续打印'));assert.equal(t.el('stopQueue').hidden,false);t.el('stopQueue').click();assert.equal(t.el('actionDialog').open,true);assert.equal(t.requests.filter(r=>r.action==='stop_queue').length,0);t.el('cancelAction').click();assert.equal(t.requests.filter(r=>r.action==='stop_queue').length,0)}finally{t.close()}
});
test('history filter only displays finished jobs',async()=>{
 const s=fixture();s.data.jobs[1].status='已完成';const t=launch(s);try{assert.equal(t.el('jobs').querySelectorAll('article').length,1);t.el('historyTab').click();assert.match(t.el('jobs').textContent,/中部2/);assert.ok(!t.el('jobs').textContent.includes('中部1'));assert.equal(t.el('historyHint').hidden,false)}finally{t.close()}
});
test('untrusted model names render as text',async()=>{
 const s=fixture();s.data.jobs[0].name='<img src=x onerror=alert(1)>.3mf';const t=launch(s);try{assert.match(t.el('jobs').textContent,/<img src=x/);assert.equal(t.el('jobs').querySelectorAll('img').length,2);assert.equal(t.el('jobs').querySelector('[onerror]'),null)}finally{t.close()}
});
test('AMS swatches distinguish black white empty and unknown colors without guessing',async()=>{
 const s=amsFixture();s.connection.devices[0].slots.push(fixture().connection.devices[0].slots[1]);s.connection.devices[0].slots[0].color='#FFFFFFFF';s.connection.devices[0].slots[1].color='#000000FF';s.connection.devices[0].slots[2].color='#00000000';s.connection.devices[0].slots[3].present=false;
 const t=launch(s);try{const slots=[...t.el('deviceTelemetry').querySelectorAll('.slot')];assert.equal(slots.length,4);assert.equal(slots[0].querySelector('.slot-color').style.backgroundColor,'rgb(255, 255, 255)');assert.equal(slots[1].querySelector('.slot-color').style.backgroundColor,'rgb(0, 0, 0)');assert.ok(slots[2].querySelector('.unknown-color'));assert.ok(slots[3].querySelector('.empty-color'));assert.match(slots[3].textContent,/空槽/);assert.match(slots[0].getAttribute('aria-label'),/AMS 1 \/ 1.*PETG.*有料/);const external=t.el('deviceTelemetry').querySelector('.external-slot');assert.equal(external.querySelector('.slot-color').style.backgroundColor,'rgb(189, 190, 189)');assert.match(external.textContent,/未送入/);assert.equal(t.requests.filter(r=>['start','save_settings'].includes(r.action)).length,0)}finally{t.close()}
});
test('color choices show actual slots and only commit selection on Save',async()=>{
 const s=amsFixture();s.connection.devices[0].slots[1].color='#00A0FFFF';s.connection.devices[0].slots[3].type='PLA';const t=launch(s);
 try{t.el('startQueue').click();const choices=t.el('materialMappings').querySelectorAll('[data-material-slot]');assert.equal(choices.length,4);assert.equal(choices[1].querySelector('.slot-color').style.backgroundColor,'rgb(0, 160, 255)');assert.equal(choices[3].disabled,true);choices[1].focus();choices[1].click();const selected=t.el('materialMappings').querySelector('[aria-pressed=true]');assert.equal(selected.dataset.materialSlot,'ams/0/tray/1');assert.equal(t.w.document.activeElement,selected);assert.equal(t.requests.filter(r=>r.action==='save_settings').length,0);t.el('savePrintSettings').click();await tick();assert.equal(t.requests.find(r=>r.action==='save_settings').settings.mapping['9'],'ams/0/tray/1')}finally{t.close()}
});
test('current model stays above both queue tabs and is never duplicated',async()=>{
 const s=multiFixture(),t=launch(s);try{assert.equal(t.el('currentTaskPanel').hidden,false);assert.equal(t.el('currentJob').querySelectorAll('article').length,1);assert.equal(t.el('currentJob').querySelector('article').dataset.id,'job1');assert.ok(![...t.el('jobs').querySelectorAll('article')].some(e=>e.dataset.id==='job1'));assert.equal(t.el('pendingCount').textContent,'1');t.el('historyTab').click();assert.equal(t.el('currentJob').querySelector('article').dataset.id,'job1');assert.equal(t.el('currentJob').querySelector('.delete-task'),null)}finally{t.close()}
});
test('P1S ending and stopping explain the target printer and manual plate change',async()=>{
 const s=multiFixture();s.queue_states['fixture-p1'].data.active={job_id:'p1-job1',kind:'model',identity:{subtask_id:'p1-task'}};s.queue_states['fixture-p1'].data.jobs[0].status='打印中';s.queue_states['fixture-p1'].data.phase='monitoring';s.queue_states['fixture-p1'].data.running=true;
 const t=launch(s);try{t.w.selectQueue('fixture-p1');await tick();t.w.confirmControl('end_current');assert.match(t.el('actionTitle').textContent,/P1S/);assert.match(t.el('actionDescription').textContent,/等待手动换板/);assert.ok(!t.el('actionDescription').textContent.includes('执行换盘'));t.el('cancelAction').click();t.el('stopQueue').click();assert.match(t.el('actionDescription').textContent,/其他打印机继续/);assert.equal(t.requests.filter(r=>['end_current','stop_queue'].includes(r.action)).length,0)}finally{t.close()}
});
test('imports require a target machine before opening files or transferring bytes',async()=>{
 const s=emptyImportFixture();s.data.device_id='';const t=launch(s);try{assert.equal(t.el('quickAdd').disabled,true);t.el('startQueue').click();assert.equal(t.fileClicks,0);await t.w.importFiles([{name:'test.3mf',size:1}]);t.el('path').value='E:/model.3mf';t.el('add').click();await tick();assert.equal(t.requests.filter(r=>['upload_begin','add'].includes(r.action)).length,0)}finally{t.close()}
});
test('recovery controls only appear for an interrupted active task',async()=>{
 const t=launch();try{assert.equal(t.el('recoveryPanel').hidden,true);const s=t.state();s.data.phase='recovery';s.data.active={kind:'model',job_id:'job1',identity:{subtask_id:'pending'}};t.set(s);assert.equal(t.el('recoveryPanel').hidden,false);assert.equal(t.el('recoveryPanel').open,true);assert.equal(t.el('startQueue').hidden,true);assert.equal(t.el('reviewCurrent').hidden,false)}finally{t.close()}
});
test('plate confirmation is shown only for the selected waiting machine',async()=>{
 const s=multiFixture();s.queue_states['fixture-p1'].data.phase='confirm_plate';s.fleet[1].phase='confirm_plate';const t=launch(s);try{assert.equal(t.el('confirmPlate').hidden,true);assert.match(t.el('fleetQueues').textContent,/等待换板/);t.w.selectQueue('fixture-p1');await tick();assert.equal(t.el('confirmPlate').hidden,false);assert.equal(t.el('swapContinue').hidden,true);assert.equal(t.requests.filter(r=>r.action==='confirm_plate').length,0);assert.equal(t.el('commandDevice').textContent,'P1S')}finally{t.close()}
});
test('unknown AMS colors cannot introduce page markup or CSS',async()=>{
 const s=amsFixture();s.connection.devices[0].slots[0].color='red; background-image:url(https://invalid/)';s.connection.devices[0].slots[0].label='<img onerror=x>';
 const t=launch(s);try{const slot=t.el('deviceTelemetry').querySelector('.slot');assert.ok(slot.querySelector('.unknown-color'));assert.equal(slot.querySelector('.slot-color').style.backgroundColor,'');assert.equal(slot.querySelector('img'),null);assert.equal(slot.querySelector('[onerror]'),null)}finally{t.close()}
});
test('idle devices with HMS alerts pass idle checks but fail the separate alert check',async()=>{
 const s=fixture();s.connection.devices[0].telemetry.hms_count=1;const t=launch(s);try{assert.match(t.el('bridgeNotice').textContent,/没有运行中的打印任务.*1 条 HMS/);const checks=t.w.startChecks(s.data);assert.equal(checks[0][1],true);assert.equal(checks[1][1],false);assert.match(checks[1][2],/设备 → 助手/);t.preflightError='当前没有运行中的打印任务，但设备仍报告：1 条 HMS 设备告警。';t.w.openStart('start');await tick();assert.match(t.el('startChecklist').textContent,/1 条 HMS/);assert.ok(!t.el('startChecklist').textContent.includes('结束或处理当前任务'));t.el('bedClear').checked=true;t.el('bedClear').dispatchEvent(new t.w.Event('change'));assert.equal(t.el('confirmStart').disabled,true);assert.equal(t.requests.filter(r=>r.action==='start').length,0)}finally{t.close()}
});
test('print error codes are visible and idle status is not changed by errors',async()=>{
 const s=fixture();s.connection.devices[0].telemetry.print_error=0x03008004;const t=launch(s);try{assert.match(t.el('bridgeNotice').textContent,/0x03008004/);assert.equal(t.w.startChecks(s.data)[0][1],true);assert.equal(t.w.startChecks(s.data)[1][1],false);s.connection.devices[0].telemetry.print_error=0;t.set(s);assert.equal(t.el('bridgeNotice').hidden,true);assert.equal(t.w.startChecks(s.data)[1][1],true)}finally{t.close()}
});
test('busy and stale device reasons are distinct from HMS alerts',async()=>{
 const t=launch();try{const s=t.state();s.connection.devices[0].telemetry.gcode_state='RUNNING';t.set(s);assert.match(t.w.startChecks(s.data)[0][2],/运行中或暂停的任务/);assert.equal(t.w.startChecks(s.data)[1][1],true);s.connection.devices[0].state_age_ms=20000;t.set(s);assert.match(t.w.startChecks(s.data)[0][2],/刷新本机状态/)}finally{t.close()}
});
function objectPreviewFixture(objects){return {available:true,top:png,width:512,height:512,note:'已核对本盘拾取图',regions:objects.map((o,i)=>({id:String(o.id),path:'M'+(100+i*40)+' 100h20v20h-20z',box:[100+i*40,100,120+i*40,120],center:[110+i*40,110]}))}}
function skipFixture(){const s=fixture();s.data.running=true;s.data.phase='monitoring';s.data.active={kind:'model',job_id:'job1',request_id:'request-one',tag:'oq_one',identity:{subtask_id:'task-one'}};s.data.jobs[0].status='打印中';s.connection.devices[0].telemetry.gcode_state='RUNNING';return s}
function clickObject(t,id){t.el('objectsPreview').querySelector('[data-object-id="'+id+'"]').dispatchEvent(new t.w.MouseEvent('click',{bubbles:true}))}
test('picture selection and checkboxes stay synchronized without sending until confirmation',async()=>{
 const t=launch(skipFixture());try{await t.w.openObjects();assert.equal(t.el('objectsDialog').open,true);assert.equal(t.el('objectsPreview').querySelectorAll('.object-hit').length,2);assert.equal(t.el('confirmSkip').disabled,true);clickObject(t,'1419');assert.equal(t.el('objectsList').querySelector('input[value="1419"]').checked,true);assert.match(t.el('objectsSelected').textContent,/1 \/ 2/);assert.equal(t.el('objectsList').querySelectorAll('.object-thumb svg image').length,2);t.el('objectsList').querySelector('input[value="1419"]').click();assert.ok(!t.el('objectsPreview').querySelector('[data-object-id="1419"]').classList.contains('selected-object'));t.el('objectsList').querySelector('input[value="1420"]').click();assert.ok(t.el('objectsPreview').querySelector('[data-object-id="1420"]').classList.contains('selected-object'));assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0);t.el('confirmSkip').click();await tick();assert.deepEqual(t.requests.find(r=>r.action==='skip_objects').objects,[1420]);assert.equal(t.el('objectsDialog').open,false)}finally{t.close()}
});
test('hovering the preview highlights its row and list hover highlights its exact native mask',async()=>{
 const t=launch(skipFixture());try{await t.w.openObjects();const hit=t.el('objectsPreview').querySelector('[data-object-id="1419"]');hit.dispatchEvent(new t.w.MouseEvent('mouseenter'));assert.ok(t.el('objectsList').querySelector('[data-object-id="1419"]').classList.contains('hover-object'));const row=t.el('objectsList').querySelector('[data-object-id="1420"]');row.dispatchEvent(new t.w.MouseEvent('mouseenter'));assert.ok(t.el('objectsPreview').querySelector('[data-object-id="1420"]').classList.contains('hover-object'));assert.equal(t.el('objectsSelected').textContent,'0 / 2 已选');t.el('objectsFit').click();assert.notEqual(t.el('objectsPreview').querySelector('svg').getAttribute('viewBox'),'0 0 512 512');t.el('objectsWhole').click();assert.equal(t.el('objectsPreview').querySelector('svg').getAttribute('viewBox'),'0 0 512 512')}finally{t.close()}
});
test('already skipped objects are locked and selecting the last object makes ending explicit',async()=>{
 const s=skipFixture();s.data.active.skipped=[1419];const t=launch(s);try{await t.w.openObjects();const first=t.el('objectsList').querySelector('input[value="1419"]');assert.equal(first.disabled,true);assert.equal(first.checked,true);clickObject(t,'1419');assert.equal(t.el('objectsSelected').textContent,'0 / 1 已选');t.el('objectsSelectAll').click();assert.equal(t.el('objectsSelectAll').checked,true);assert.match(t.el('confirmSkip').textContent,/结束本盘/);assert.match(t.el('objectsConsequence').textContent,/全部剩余零件/);assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0);t.el('confirmSkip').click();await tick();assert.deepEqual(t.requests.find(r=>r.action==='skip_objects').objects,[1420])}finally{t.close()}
});
test('polling preserves selection and new Handy skips update disabled objects',async()=>{
 const t=launch(skipFixture());try{await t.w.openObjects();clickObject(t,'1419');t.set(t.state());assert.equal(t.el('objectsList').querySelector('input[value="1419"]').checked,true);const s=t.state();s.connection.devices[0].telemetry.s_obj=[1419];t.set(s);assert.equal(t.el('objectsList').querySelector('input[value="1419"]').disabled,true);assert.equal(t.el('objectsSelected').textContent,'0 / 1 已选');s.data.active.pending_skip={objects:[1419,1420]};t.set(s);assert.equal(t.el('objectsList').querySelector('input[value="1420"]').disabled,true);assert.match(t.el('objectsList').textContent,/待设备确认/);assert.equal(t.el('confirmSkip').disabled,true);assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0)}finally{t.close()}
});
test('changing active print identity closes the old selection dialog',async()=>{
 const t=launch(skipFixture());try{await t.w.openObjects();clickObject(t,'1419');const s=t.state();s.data.active.identity={subtask_id:'different-task'};t.set(s);assert.equal(t.el('objectsDialog').open,false);assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0)}finally{t.close()}
});
test('unmapped or missing masks fall back to the real checkbox list without guessing positions',async()=>{
 for(const value of [{available:false,note:'缺少拾取图'}, {...objectPreviewFixture(fixture().data.jobs[0].objects),regions:[{id:'999',path:'M1 1h2v2h-2z',box:[1,1,3,3]}]}]){const s=skipFixture();s.object_preview=value;const t=launch(s);try{await t.w.openObjects();assert.equal(t.el('objectsPreview').querySelectorAll('.object-hit').length,0);assert.equal(t.el('objectsFit').disabled,true);assert.equal(t.el('objectsList').querySelectorAll('input').length,2);t.el('objectsList').querySelector('input').click();assert.equal(t.el('confirmSkip').disabled,false)}finally{t.close()}}
});
test('waiting task preview and selection never enable a skip command',async()=>{
 const t=launch();try{await t.w.openObjects('job1',true);assert.match(t.el('objectsTitle').textContent,/预览/);clickObject(t,'1419');assert.equal(t.el('confirmSkip').hidden,true);assert.equal(t.el('objectsReadOnly').hidden,false);t.el('confirmSkip').click();await tick();assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0);assert.deepEqual(t.state().data.jobs.map(j=>j.status),['等待','等待'])}finally{t.close()}
});
test('late preview results cannot populate a newly opened different object dialog',async()=>{
 const t=launch(skipFixture());try{t.deferPreview=true;const first=t.w.openObjects();t.el('closeObjects').click();const second=t.w.openObjects('job2',true);t.flushPreview();await first;assert.equal(t.el('objectsPreview').querySelectorAll('.object-hit').length,0);assert.match(t.el('objectsDescription').textContent,/中部2/);t.flushPreview();await second;assert.equal(t.el('objectsPreview').querySelectorAll('.object-hit').length,2);assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0)}finally{t.close()}
});
test('missing native object labels allow ending the whole plate but not a partial skip',async()=>{
 const s=skipFixture();s.data.jobs[0].label_markers=false;const t=launch(s);try{await t.w.openObjects();clickObject(t,'1419');assert.equal(t.el('confirmSkip').disabled,true);assert.match(t.el('objectsConsequence').textContent,/缺少原生/);t.el('objectsSelectAll').click();assert.equal(t.el('confirmSkip').disabled,false);assert.match(t.el('confirmSkip').textContent,/结束本盘/)}finally{t.close()}
});
test('offline printers allow inspecting objects but cannot submit selected skips',async()=>{
 const s=skipFixture();s.connection.devices[0].online=false;const t=launch(s);try{await t.w.openObjects();clickObject(t,'1419');assert.equal(t.el('confirmSkip').disabled,true);assert.match(t.el('objectsConsequence').textContent,/恢复连接并核对/);t.el('confirmSkip').click();assert.equal(t.requests.filter(r=>r.action==='skip_objects').length,0);s.connection.devices[0].online=true;t.set(s);assert.equal(t.el('confirmSkip').disabled,false);assert.equal(t.el('objectsList').querySelector('input[value="1419"]').checked,true)}finally{t.close()}
});
test('completion verification is shown as automatic state checking rather than printing at 100 percent',async()=>{
 const s=fixture();s.data.running=true;s.data.phase='monitoring';s.data.reason='正在补齐本盘的启动与完成记录，后续任务暂不发送。';s.data.active={kind:'model',job_id:'job1',identity:{subtask_id:'actual'},seen_running:true,monitor:{stage:'verifying_finish'}};s.data.jobs[0].status='打印中';s.connection.devices[0].telemetry.gcode_state='FINISH';s.connection.devices[0].telemetry.mc_percent=100;const t=launch(s);try{assert.equal(t.el('phaseBadge').textContent,'正在确认完成');assert.match(t.el('runStatus').textContent,/正在补齐本盘/);assert.equal(t.el('recoveryPanel').hidden,true);assert.equal(t.el('completeContinue').hidden,true);assert.equal(t.requests.some(r=>['complete_continue','start'].includes(r.action)),false)}finally{t.close()}
});
test('temporary connection recovery retains the active job without exposing manual completion',async()=>{
 const s=fixture();s.data.running=true;s.data.phase='monitoring';s.data.reason='连接暂时中断，正在重新读取本盘状态；后续任务暂不发送。';s.data.active={kind:'model',job_id:'job1',identity:{subtask_id:'actual'},seen_running:true,monitor:{stage:'reconnecting'}};s.data.jobs[0].status='打印中';s.connection.devices[0].online=false;const t=launch(s);try{assert.equal(t.el('phaseBadge').textContent,'正在恢复连接');assert.match(t.el('runStatus').textContent,/连接暂时中断/);assert.equal(t.el('recoveryPanel').hidden,true);assert.equal(t.el('startQueue').hidden,true)}finally{t.close()}
});
function completedRecoveryFixture(){const s=fixture();s.data.phase='recovery';s.data.active={kind:'model',job_id:'job1',request_id:'attempt-finished',tag:'oq_finished',identity:{subtask_id:'old'},seen_running:false};s.data.jobs[0].status='发送中';s.connection.devices[0].telemetry={gcode_state:'FINISH',mc_percent:100,subtask_name:'oq_finished',subtask_id:'actual',print_error:0};s.setup.job2={configured:true,ready:true};return s}
test('finished recovery exposes completion review and disables looping monitor recovery',async()=>{
 const t=launch(completedRecoveryFixture());try{assert.equal(t.el('completeContinue').hidden,false);assert.equal(t.el('completeContinue').disabled,false);assert.equal(t.el('resumeMonitor').disabled,true);assert.equal(t.requests.some(r=>r.action==='complete_continue'),false);assert.ok([...t.el('currentJob').querySelectorAll('button')].filter(b=>/暂停打印|结束本盘/.test(b.textContent)).every(b=>b.disabled))}finally{t.close()}
});
test('completion review checks the frozen attempt and requires user confirmation before continuing',async()=>{
 const t=launch(completedRecoveryFixture());try{t.el('completeContinue').click();await tick();assert.equal(t.el('completeDialog').open,true);assert.equal(t.el('confirmComplete').disabled,true);assert.equal(t.requests.find(r=>r.action==='preflight').attempt_id,'attempt-finished');assert.match(t.el('completeDescription').textContent,/独立换盘/);t.el('completeConfirmed').click();assert.equal(t.el('confirmComplete').disabled,false);t.el('confirmComplete').click();await tick();const request=t.requests.find(r=>r.action==='complete_continue');assert.equal(request.attempt_id,'attempt-finished');assert.equal(request.confirmed,true);assert.equal(t.requests.some(r=>['start','end_current','stop_queue'].includes(r.action)),false)}finally{t.close()}
});
test('completion review does not continue after a failed preflight',async()=>{
 const t=launch(completedRecoveryFixture());try{t.preflightError='换盘文件失效';t.el('completeContinue').click();await tick();t.el('completeConfirmed').click();assert.equal(t.el('confirmComplete').disabled,true);assert.match(t.el('completeError').textContent,/换盘文件失效/);assert.equal(t.requests.some(r=>r.action==='complete_continue'),false)}finally{t.close()}
});
test('a different active attempt invalidates an open completion confirmation',async()=>{
 const t=launch(completedRecoveryFixture());try{t.el('completeContinue').click();await tick();t.el('completeConfirmed').click();const s=t.state();s.data.active.request_id='another-attempt';t.set(s);assert.equal(t.el('confirmComplete').disabled,true);assert.match(t.el('completeError').textContent,/任务已变化/);t.el('confirmComplete').click();await tick();assert.equal(t.requests.some(r=>r.action==='complete_continue'),false)}finally{t.close()}
});
test('late completion checks cannot approve a reopened dialog',async()=>{
 const t=launch(completedRecoveryFixture());try{t.deferPreflight=true;t.el('completeContinue').click();t.el('closeComplete').click();t.el('completeContinue').click();t.el('completeConfirmed').click();t.flushPreflight();await tick();assert.equal(t.el('confirmComplete').disabled,true);t.flushPreflight();await tick();assert.equal(t.el('confirmComplete').disabled,false)}finally{t.close()}
});
test('manual completion recovery waits for board confirmation instead of promising automatic swap',async()=>{
 const s=completedRecoveryFixture();s.data.plate_mode='manual';const t=launch(s);try{t.el('completeContinue').click();await tick();assert.match(t.el('completeDescription').textContent,/等待手动更换打印板/);assert.ok(!t.el('completeConfirmationText').textContent.includes('备板'))}finally{t.close()}
});
test('completed recovery cannot be submitted if the device becomes stale or faults',async()=>{
 const t=launch(completedRecoveryFixture());try{t.el('completeContinue').click();await tick();t.el('completeConfirmed').click();const s=t.state();s.connection.devices[0].state_age_ms=20000;t.set(s);assert.equal(t.el('confirmComplete').disabled,true);s.connection.devices[0].state_age_ms=0;s.connection.devices[0].telemetry.print_error=123;t.set(s);assert.equal(t.el('confirmComplete').disabled,true)}finally{t.close()}
});
function bundledFixture(){const s=fixture();s.components={available:true,ready:false,installed:false,can_install:true,restore_available:false,summary:'尚未安装连接组件',note:'Windows x64',series:[{series:'02.03.00',kind:'open_bamboo',compatible:false,loaded:true},{series:'02.08.04',kind:'missing',compatible:false,loaded:false}]};s.default_swap_available=false;return s}





test('update status verifies both page service build and loaded history capability',async()=>{
 const s=fixture();s.build_id='20261102.1';s.connection.devices[0].monitor_epoch='loaded-native-epoch';const t=launch(s);try{assert.match(t.el('buildLabel').textContent,/精简队列版.*20261102.1/);assert.match(t.el('buildService').textContent,/已更新.*20261102.1/);assert.equal(t.el('buildHistory').textContent,'连接组件：状态历史已启用');assert.match(t.el('connectionStatus').textContent,/状态历史已启用/)}finally{t.close()}
});
test('new page cannot mistake an old loaded bridge for a complete update',async()=>{
 const s=fixture();s.build_id='20261102.1';const t=launch(s);try{assert.match(t.el('buildService').textContent,/已更新/);assert.match(t.el('buildHistory').textContent,/旧桥接.*完整重启/);assert.match(t.el('connectionStatus').textContent,/旧连接组件/)}finally{t.close()}
});
test('unmatched service or unavailable printer reports unknown update state clearly',async()=>{
 const s=fixture();s.connection={available:false,devices:[],reason:'未登录'};const t=launch(s);try{assert.match(t.el('buildService').textContent,/尚未匹配/);assert.equal(t.el('buildHistory').textContent,'连接组件：等待打印机状态');assert.equal(t.requests.some(r=>r.action==='connection_install'),false)}finally{t.close()}
});
test('AMS readiness checks the actually loaded material bridge separately from history',async()=>{
 const s=fixture();s.build_id='20261102.1';s.connection.devices[0].monitor_epoch='loaded-history';const t=launch(s);try{assert.match(t.el('buildMaterials').textContent,/旧组件.*完整重启/);s.connection.material_mapping_ready=true;t.set(s);assert.equal(t.el('buildMaterials').textContent,'耗材映射：完整 AMS 映射已启用');assert.equal(t.requests.some(r=>['start','submit'].includes(r.action)),false)}finally{t.close()}
});
test('native binding failure is shown separately from waiting for telemetry',async()=>{
 const s=fixture();s.build_id='20261102.1';s.connection={available:false,devices:[],error_code:'native_binding_failed',reason:'无法绑定 Orca 已加载的连接组件（TypeError）。请更新队列插件并完整退出、重启 Orca。'};const t=launch(s);try{assert.match(t.el('buildHistory').textContent,/绑定失败/);assert.equal(t.el('buildMaterials').textContent,'耗材映射：等待桥接恢复');assert.match(t.el('bridgeNotice').textContent,/TypeError/);assert.equal(t.requests.some(r=>['start','submit','connection_install'].includes(r.action)),false)}finally{t.close()}
});
test('connection guide is read-only in both local and cloud variants',async()=>{
 for(const state of [fixture(),bundledFixture()]){const t=launch(state);try{assert.equal(t.el('openConnection').hidden,false);assert.equal(t.w.document.getElementById('installComponents'),null);assert.equal(t.w.document.getElementById('restoreComponents'),null);t.el('openConnection').click();await tick();assert.equal(t.el('connectionDialog').open,true);assert.match(t.el('connectionDialog').textContent,/独立安装/);assert.equal(t.requests.some(r=>/^connection_/.test(r.action)),false);t.el('closeConnection').click();assert.equal(t.el('connectionDialog').open,false)}finally{t.close()}}
});
test('legacy component state cannot enable an installation action',async()=>{
 const s=bundledFixture();s.components.can_install=true;s.components.restore_available=true;s.components.ready=true;const t=launch(s);try{t.el('openConnection').click();await tick();assert.equal(t.w.document.getElementById('installComponents'),null);assert.equal(t.requests.some(r=>['connection_install','connection_restore'].includes(r.action)),false);assert.match(t.el('componentNote').textContent,/不安装、替换或恢复/)}finally{t.close()}
});

test('connection downloads use a pinned public release without installer commands',async()=>{
 const t=launch();try{t.el('openConnection').click();await tick();const link=t.el('downloadConnection');assert.equal(link.href,'https://github.com/ChenLei0504/orca-plate-queue/releases/download/v0.7.3/Orca-Queue-Connection-0.7.3-Windows-x64.zip');assert.equal(link.target,'_blank');assert.match(link.rel,/noopener/);assert.match(t.el('connectionRelease').href,/\/releases\/tag\/v0\.7\.3$/);const field=t.el('connectionDownloadUrl');assert.equal(field.readOnly,true);assert.equal(field.value,link.href);field.click();assert.equal(field.selectionStart,0);assert.equal(field.selectionEnd,field.value.length);assert.equal(t.requests.some(r=>['connection_install','connection_restore','submit'].includes(r.action)),false)}finally{t.close()}
});
module.exports={fixture,multiFixture,amsFixture,emptyImportFixture,bundledFixture};
if(require.main===module)(async()=>{for(const [name,fn] of tests){await fn();console.log('PASS',name)}console.log(tests.length+' page workflow tests passed; no real printer calls.');})().catch(e=>{console.error(e);process.exitCode=1});
