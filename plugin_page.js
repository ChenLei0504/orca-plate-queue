/* Local Orca page bridge. No credentials or HTTP file uploads in this page. */
const PAGE_BUILD_ID='20261101.2';
let latestReply=null,connection={available:false,devices:[]},setup={},swapSettings={},transitions=[];
let selected=null,busy=false,draggingId=null,pointerDragging=false,editing=null,swapDirty=false;
let requestSequence=0,toastTimer=null,cardsKey='',queueFilter='pending',actionIntent=null;
const noticedImports=new Set();
let viewQueueId=null,switchingQueue=false,fleetKey='';
let objectsState=null,objectsSerial=0;
const SWAP_MODELS=new Set(['N2S']);
const MODEL_NAMES={'N2S':'A1','C12':'P1S'};
let startOperation='start',startEpoch=0,startPassed=false,startChecking=false;
let completionAttempt=null;
const pendingRequests=new Map(),$=id=>document.getElementById(id),clone=value=>JSON.parse(JSON.stringify(value));
const READY_STATES=new Set(['IDLE','FINISH','FAILED']);
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function icon(name){const e=document.createElementNS('http://www.w3.org/2000/svg','svg');e.setAttribute('class','icon');e.setAttribute('aria-hidden','true');const use=document.createElementNS(e.namespaceURI,'use');use.setAttribute('href','#i-'+name);e.append(use);return e}
function button(text,cls,fn,label){const b=node('button',cls,text);b.type='button';if(label)b.setAttribute('aria-label',label);b.onclick=fn;return b}
function pill(text,tone=''){return node('span','status-pill'+(tone?' '+tone:''),text)}
function setPill(id,text,tone=''){const e=$(id);e.className='status-pill'+(tone?' '+tone:'');e.textContent=text}
function renderComponents(reply){
  $('openConnection').hidden=false;
  $('defaultSwap').hidden=reply?.default_swap_available===false;
  const connected=reply?.connection?.available===true;
  $('componentSummary').textContent=connected?'已复用 Orca 当前连接组件与 Bambu Cloud 登录会话。':'尚未连接。首次使用请单独安装连接组件。';
  $('componentSeries').textContent='支持 Windows x64 · 接口 02.03.00 / 02.08.01 / 02.08.04';
  $('componentNote').textContent='队列插件只使用 Orca 已加载的连接组件，不安装、替换或恢复联网文件。连接组件需要更新时，请退出 Orca 后使用独立安装器。';
}
function basename(path){return String(path||'').split(/[\\/]/).pop()||''}
function validColor(value){return /^#[\da-f]{6}([\da-f]{2})?$/i.test(value||'')}
function displayColor(color){return validColor(color)&&!(color.length===9&&color.slice(-2)==='00')?color.slice(0,7).toUpperCase():''}
function swatch(color){const e=node('span','material-color'),value=displayColor(color);if(value)e.style.backgroundColor=value;else e.classList.add('unknown-color');e.title=value||'颜色未知';return e}
function slotColor(slot){const chip=node('span','slot-color'),value=slot.kind==='ams'&&slot.present===false?'':displayColor(slot.color);if(value)chip.style.backgroundColor=value;else chip.classList.add(slot.kind==='ams'&&slot.present===false?'empty-color':'unknown-color');chip.setAttribute('aria-hidden','true');return chip}
function slotState(slot){return slot.present===false?(slot.kind==='external'?'未送入':'空槽'):slot.present===true?(slot.kind==='external'?'已送入':'有料'):'待确认'}
function slotShortLabel(slot){return slot.kind==='external'?'外挂':slot.label.replace(/^AMS\s*/,'').replace(/\s*\/\s*/,' · ')}
function duration(value){if(value===null||value===undefined||!Number.isFinite(Number(value)))return '耗时未知';const m=Math.round(Number(value)/60);return (m>=60?Math.floor(m/60)+' 小时 ':'')+m%60+' 分钟'}
function pendingJobs(data=latestReply?.data){return (data?.jobs||[]).filter(j=>j.status==='等待')}
function boundDevice(data=latestReply?.data){return connection.devices.find(d=>d.id===data?.device_id&&MODEL_NAMES[d.model])}
function deviceFaultText(d){const t=d?.telemetry||{},details=[],error=t.print_error,count=t.hms_count;if(error)details.push('打印错误 '+(Number.isInteger(error)&&error>=0?'0x'+error.toString(16).toUpperCase().padStart(8,'0'):String(error)));if(count)details.push(count+' 条 HMS 设备告警');return details.join('；')}
function deviceReady(d){return !!d&&!!MODEL_NAMES[d.model]&&d.online&&d.cloud_connected&&d.age_ms<=15000&&d.nozzle!==null}
function feedback(message,error=false){if(!message)return;clearTimeout(toastTimer);const box=$('feedback');box.replaceChildren(button('×','',()=>{box.hidden=true},'关闭提示'),document.createTextNode(message));box.className='toast'+(error?' error':'');box.hidden=false;if(!error)toastTimer=setTimeout(()=>{box.hidden=true},6500)}
function send(action,extra={}){
  if(!window.orca)return Promise.resolve({success:false,note:'请在 Orca 中使用此页面。'});
  const request_id=String(++requestSequence);
  return new Promise(resolve=>{
    const timer=setTimeout(()=>{pendingRequests.delete(request_id);resolve({success:false,note:'暂未确认操作结果，请先刷新队列，不要重复提交。'})},45000);
    pendingRequests.set(request_id,{resolve,timer,action,queue_id:viewQueueId});
    try{orca.postMessage({action,...extra,request_id,...(viewQueueId!==null?{queue_id:viewQueueId}:{})})}catch(e){clearTimeout(timer);pendingRequests.delete(request_id);resolve({success:false,note:e.message||'页面连接中断'})}
  });
}
async function checkedSend(action,data){const reply=await send(action,data);if(!reply.success)throw new Error(reply.note||'操作失败');return reply}
async function perform(action,data={},element=null){if(element?.disabled)return;const disabled=element?.disabled;if(element)element.disabled=true;try{return await checkedSend(action,data)}catch(e){feedback(e.message,true);return null}finally{if(element){element.disabled=disabled;if(latestReply)renderRun(latestReply.data)}}}
function clearDropHints(){document.querySelectorAll('.drop-before,.drop-after').forEach(e=>e.classList.remove('drop-before','drop-after'))}
function isFileDrag(e){return Array.from(e.dataTransfer?.types||[]).includes('Files')}
function finishDragging(){draggingId=null;clearDropHints();document.querySelectorAll('.moving').forEach(e=>e.classList.remove('moving'));if(latestReply&&!busy)applyState(latestReply)}
function scrollToPanel(id){const e=$(id);e.scrollIntoView({behavior:'smooth',block:'center'});return e}
function focusDevice(){scrollToPanel('printerFleet');const first=$('fleetQueues').querySelector('button:not(:disabled)');if(first)first.focus();else feedback('请先在 Orca 首页登录 Bambu Cloud，并确认 A1 或 P1S 在线。',true)}
async function selectQueue(device_id){if(busy||switchingQueue||device_id===viewQueueId)return;switchingQueue=true;if(latestReply)renderFleet(latestReply);try{await checkedSend('select_queue',{device_id})}catch(e){feedback(e.message,true)}finally{switchingQueue=false;if(latestReply){$('quickAdd').disabled=busy||!boundDevice();renderFleet(latestReply)}}}
function machineStatus(q,d){
  if(q?.running&&['syncing','verifying_finish','reconnecting'].includes(q.monitor_stage))return [q.monitor_stage==='reconnecting'?'正在恢复连接':q.monitor_stage==='verifying_finish'?'正在确认完成':'正在核对状态','warning'];
  if(q?.phase==='recovery')return ['需要核对','error'];
  if(q?.phase==='confirm_plate')return ['等待换板','warning'];
  if(!d.online)return ['离线','muted'];
  if(!q&&['RUNNING','PAUSE','PREPARE'].includes(d.telemetry?.gcode_state))return ['设备有打印任务','warning'];
  if(q?.active&&d.telemetry?.gcode_state==='PAUSE')return ['打印已暂停','warning'];
  if(q?.running)return [q.phase==='sending'?'正在发送':q.phase==='between'?'准备换盘':q.phase==='monitoring'?'打印中':'队列运行中',''];
  if(q?.active)return ['需要核对','warning'];
  return [q?.pending?'队列待开始':'空闲','muted'];
}
function renderFleet(reply){
  const body=$('fleetQueues'),managed=new Map((reply.fleet||[]).map(q=>[q.id,q])),rows=new Map(connection.devices.filter(d=>MODEL_NAMES[d.model]).map(d=>[d.id,d]));
  for(const q of managed.values())if(!rows.has(q.id))rows.set(q.id,q);
  const entries=[...rows].map(([id,d])=>{const q=managed.get(id),status=machineStatus(q,d),progress=q?.active&&typeof d.telemetry?.mc_percent==='number'?Math.max(0,Math.min(100,d.telemetry.mc_percent)):null;return {id,name:d.name,model:d.model,q,status,progress}});
  const key=JSON.stringify([entries,reply.data.device_id,busy,switchingQueue]);$('fleetCount').textContent=rows.size+' 台';
  if(key===fleetKey)return;fleetKey=key;
  const focused=document.activeElement?.closest('#fleetQueues button')?.dataset.deviceId;body.replaceChildren();
  if(!rows.size){body.append(node('p','fleet-empty','登录 Bambu Cloud 后，这里会显示你的 A1 和 P1S。'));return}
  for(const {id,name,model,q,status,progress} of entries){
    const b=button('','fleet-machine'+(id===reply.data.device_id?' current-machine':''),()=>selectQueue(id),'查看 '+name+' 的队列');b.dataset.deviceId=id;b.disabled=busy||switchingQueue;b.setAttribute('aria-pressed',String(id===reply.data.device_id));
    const top=node('span','fleet-machine-top'),glyph=node('span','machine-glyph');glyph.append(icon('printer'));top.append(glyph,node('strong','',name));b.append(top,node('small','machine-model',(MODEL_NAMES[model]||model||'打印机')+' · '+id.slice(-4)),pill(...status),node('small','machine-count',q?q.pending+' 盘等待'+(q.drafts?' · '+q.drafts+' 个待配置':''):'点击建立独立队列'));
    if(progress!==null){const track=node('span','machine-progress'),fill=node('span');fill.style.width=progress+'%';track.append(fill);b.append(track,node('small','',progress+'%'))}
    body.append(b);
  }
  if(focused){const target=[...body.querySelectorAll('button')].find(b=>b.dataset.deviceId===focused);if(target&&!target.disabled)target.focus({preventScroll:true})}
}
function materialKey(asset){return JSON.stringify([asset.printer,Number(asset.nozzle),[...(asset.filaments||[])].map(f=>[String(f.id),String(f.type||'').trim().toUpperCase(),String(f.color||'').toUpperCase(),f.profile_id||'',Number(f.nozzle)]).sort((a,b)=>a[0].localeCompare(b[0]))])}
function materialText(job){const s=job.settings||{},d=connection.devices.find(d=>d.id===s.device_id),mapping=(job.status==='等待'?setup[job.id]?.resolved_mapping:job.last_mapping)||s.mapping||{};if(!(job.filaments||[]).every(f=>mapping[f.id]))return '尚未配置耗材';const fallback=job.status==='等待'&&Object.keys(mapping).some(id=>mapping[id]!==s.mapping?.[id]);return (fallback?'预计使用备用槽 · ':job.last_mapping&&job.status!=='等待'?'本盘发送 · ':'')+(s.source==='external'?'外挂':'AMS')+' · '+job.filaments.map(f=>d?.slots.find(slot=>slot.id===mapping[f.id])?.label||'槽位待回报').join(' / ')+(Object.keys(s.refill||{}).length?' · 已设跨盘续料':'')}
function readiness(data,forceSwap=false){const jobs=pendingJobs(data),device=deviceReady(boundDevice(data)),configured=jobs.filter(j=>setup[j.id]?.configured).length,ready=jobs.filter(j=>setup[j.id]?.ready).length;const needSwap=data.plate_mode!=='manual'&&(jobs.length>1||forceSwap),swap=!needSwap||(swapSettings.enabled!==false&&swapSettings.validated&&latestReply?.swap_setup?.ready);return {jobs,device,configured,ready,needSwap,swap}}
function nextStep(data=latestReply?.data){if(!data)return 'device';const r=readiness(data);if(!r.device)return 'device';if(!r.jobs.length)return data.drafts?.length?'materials':'jobs';if(r.configured<r.jobs.length)return 'materials';if(!r.swap)return 'swap';return 'start'}
function guide(stage=nextStep()){
  if(stage!=='device'&&!boundDevice())return focusDevice();
  if(busy){feedback('文件正在导入，请稍后操作。');return}
  if(stage==='device')return focusDevice();
  if(stage==='jobs'){queueFilter='pending';renderJobs(latestReply?.data||{jobs:[]});scrollToPanel('dropZone');$('fileInput').click();return}
  if(stage==='materials'){const row=latestReply?.data.drafts?.[0]||pendingJobs().find(j=>!setup[j.id]?.configured)||pendingJobs()[0];if(row)openSettings(row.id);else guide('jobs');return}
  if(stage==='swap')return openSwap();
  openStart('start');
}
function renderConnection(data){
  const d=boundDevice(data),fresh=deviceReady(d),model=d?MODEL_NAMES[d.model]||d.model:'',manual=data.plate_mode==='manual';
  $('queueName').textContent=d?d.name+' 的队列':'选择打印机';
  $('queueSubtitle').textContent=d?[model,d.nozzle?d.nozzle+' mm 喷嘴':'喷嘴待回报',manual?'手动换板':data.auto_after_swap?'自动换盘并继续':'换盘后确认继续'].join(' · '):'从左侧选择 A1 或 P1S，再加入单盘切片文件';
  $('commandDevice').textContent=d?.name||'未选择打印机';$('printerName').textContent='设备与耗材';
  $('importTarget').textContent=d?'加入 '+d.name+' · 随后配置耗材和份数':'先选择打印机，再配置耗材和份数';
  $('quickAdd').disabled=!d||busy||switchingQueue;
  setPill('printerBadge',fresh?(d.telemetry?.gcode_state==='IDLE'?'空闲':'在线'):d?(d.online?'等待回报':'离线'):'未选择',fresh?'':d?'warning':'muted');
  setPill('cloudBadge',d?.cloud_connected?'Handy 云端已连接':'等待云端连接',d?.cloud_connected?'':'muted');
  $('connectionStatus').textContent=connection.available?'通过 Orca 的 Bambu Cloud 连接。':connection.reason||'正在连接打印机…';
  const serviceUpdated=latestReply?.build_id===PAGE_BUILD_ID,historyAvailable=connection.available&&!!d?.monitor_epoch;
  $('buildService').textContent=serviceUpdated?'队列服务：已更新（'+PAGE_BUILD_ID+'）':'队列服务：尚未匹配此构建，请重新加载插件';
  $('buildHistory').textContent=!connection.available||!d?'连接组件：等待打印机状态':historyAvailable?'连接组件：状态历史已启用':'连接组件：旧桥接，需更新组件并完整重启 Orca';
  $('buildMaterials').textContent=!connection.available||!d?'耗材映射：等待连接检测':connection.material_mapping_ready?'耗材映射：完整 AMS 映射已启用':'耗材映射：旧组件，需更新并完整重启 Orca';
  if(connection.available&&d)$('connectionStatus').textContent+=' '+(historyAvailable?'状态历史已启用。':'旧连接组件，需更新并重启 Orca 以启用状态历史。');
  const reason=!connection.available?(connection.reason||'正在等待 Orca 联网服务。'):data.device_id&&!fresh?'当前机器状态暂不可用。请检查电源和云端连接，再刷新本机状态。':'';
  const fault=deviceFaultText(d),faultNotice=fresh&&fault?(READY_STATES.has(d.telemetry?.gcode_state)?'当前没有运行中的打印任务，但设备仍报告：':'设备报告：')+fault+'。请在 Orca 的“设备 → 助手(HMS)”或 Handy 查看详情。':'';
  $('bridgeNotice').hidden=!(reason||faultNotice);$('bridgeNotice').textContent=reason||faultNotice;renderTelemetry(d);
}
function renderTelemetry(device){
  const body=$('deviceTelemetry');body.replaceChildren();if(!device)return;
  const t=device.telemetry||{},grid=node('div','temperature-grid');
  for(const [title,key] of [['喷嘴','nozzle_temper'],['热床','bed_temper']]){const tile=node('div','temperature-tile'),n=t[key];tile.append(node('span','',title),node('strong','',typeof n==='number'&&Number.isFinite(n)?n.toFixed(1):'—'),node('small','','°C'));grid.append(tile)}body.append(grid);
  const line=node('div','device-subline');line.append(node('span','',device.nozzle===null?'喷嘴待回报':device.nozzle+' mm 喷嘴'),node('span','',device.age_ms>15000?'回报已过期':Math.max(0,device.age_ms/1000).toFixed(0)+' 秒前更新'));body.append(line);
  const ams=device.slots.filter(s=>s.kind==='ams');
  if(ams.length){
    const groups=new Map();for(const slot of ams){const unit=slot.label.match(/^AMS\s*(\d+)/)?.[1]||'1';if(!groups.has(unit))groups.set(unit,[]);groups.get(unit).push(slot)}
    for(const [unit,slotsInUnit] of groups){const heading=node('div','slots-title');heading.append(node('strong','','AMS '+unit),node('span','','实际耗材颜色'));body.append(heading);const slots=node('div','ams-slots');
      for(const slot of slotsInUnit){const tile=node('div','slot'+(slot.present===false?' empty-slot':'')),color=displayColor(slot.color);tile.title=slot.label+' · '+(slot.type||'类型未知')+' · '+slotState(slot)+' · '+(color||'颜色未知');tile.setAttribute('aria-label',tile.title);tile.append(node('span','slot-number',slotShortLabel(slot)),slotColor(slot),node('strong','',slot.type||'—'),node('small','slot-state',slotState(slot)));slots.append(tile)}body.append(slots);
    }
  }
  for(const slot of device.slots.filter(s=>s.kind==='external')){const row=node('div','external-slot');row.append(slotColor(slot),node('div','external-name','外挂 · '+(slot.type||'类型待设置')),pill(slotState(slot),slot.present===true?'':'muted'));row.title=displayColor(slot.color)||'颜色未知';body.append(row)}
  if(device.filament_at_toolhead===0)body.append(node('p','supply-hint','喷头当前无料，可先配置，装料后开始。'));
  else if(device.age_ms>15000)body.append(node('p','supply-hint','等待最新设备回报，恢复后再开始。'));
}
function renderOverview(data){const jobs=data.jobs||[],waiting=pendingJobs(data),done=jobs.filter(j=>j.status==='已完成').length,unconfigured=waiting.filter(j=>!setup[j.id]?.configured).length;
  $('statPending').replaceChildren(document.createTextNode(String(waiting.length)),node('small','','盘'));$('statSetup').replaceChildren(document.createTextNode(String((data.drafts||[]).length)),node('small','','个'));$('statDone').replaceChildren(document.createTextNode(String(done)),node('small','','盘'));
  const valid=waiting.every(j=>typeof j.duration_s==='number'&&Number.isFinite(j.duration_s));$('statDuration').textContent=waiting.length&&valid?duration(waiting.reduce((s,j)=>s+j.duration_s,0)):'—';
  $('summary').textContent=waiting.length+' 盘待打印'+(unconfigured?' · '+unconfigured+' 盘待配置':'')+(transitions.length?' · '+transitions.length+' 次换盘':'');
  $('pendingCount').textContent=String(waiting.length);$('historyCount').textContent=String(jobs.filter(j=>['已完成','已中止'].includes(j.status)).length);
    const r=readiness(data),list=$('readinessList');list.replaceChildren();
  const checks=[['打印机已连接',r.device,'device','选择打印机'],['本盘耗材已就绪',r.jobs.length>0&&r.ready===r.jobs.length,r.jobs.length?'materials':'jobs',!r.jobs.length?'加入任务':r.configured<r.jobs.length?'配置耗材':'检查装料'],[data.plate_mode==='manual'?'手动换板模式已设置':'换盘文件已配置',r.swap,'swap',r.needSwap?'配置换盘':'本轮无需换盘']];
  let passed=0;for(const [label,good,target,note] of checks){const row=node('div','readiness-row'),mark=node('span','check-mark'+(good?' good':''));if(good){mark.append(icon('check'));passed++}else mark.textContent='·';row.append(mark,node('span','',label));row.append(good?node('small','',note==='本轮无需换盘'?note:'已完成'):button(note,'text-button',()=>guide(target)));list.append(row)}$('readinessCount').textContent=passed+' / 3';
}
function jobButton(text,action,job,cls=''){const b=button(text,cls,e=>{e.stopPropagation();if(action==='settings')openSettings(job.id);else perform(action,{id:job.id},b)},text+'：'+job.name);return b}
function renderJobs(data){if(!data)return;
  const jobs=data.jobs||[],key=JSON.stringify([queueFilter,jobs,setup,transitions,data.active,data.phase,boundDevice(data)?.telemetry?.gcode_state,Object.keys(data.previews||{})]);
  if(cardsKey===key){updateCardProgress(data);return}
  if(draggingId)return;
  cardsKey=key;const body=$('jobs'),current=$('currentJob');body.replaceChildren();current.replaceChildren();$('currentTaskPanel').hidden=!data.active;setPill('currentTaskBadge',data.phase==='recovery'?'需要核对':data.active?.kind==='swap'?'换盘任务':boundDevice(data)?.telemetry?.gcode_state==='PAUSE'?'打印已暂停':data.phase==='sending'?'正在发送':'打印中',data.phase==='recovery'?'warning':'');$('pendingTab').setAttribute('aria-selected',String(queueFilter==='pending'));$('historyTab').setAttribute('aria-selected',String(queueFilter==='history'));$('historyHint').hidden=queueFilter!=='history';
  const visible=jobs.filter(j=>j.id!==data.active?.job_id&&(queueFilter==='history'?['已完成','已中止'].includes(j.status):!['已完成','已中止'].includes(j.status)));
  if(data.active?.kind==='swap'){const item=node('div','current-swap');item.append(icon('swap'),node('strong','','正在执行本机换盘任务'),node('p','small',swapSettings.name||basename(swapSettings.source_path||swapSettings.path)));current.append(item)}
  if(!visible.length){const e=node('div','empty');e.append(icon('stack'),node('strong','',queueFilter==='history'?'还没有执行记录':'把下一盘，加入这里'),node('p','',queueFilter==='history'?'完成或中止的任务会保留在这里。':'拖入 Orca 导出的单盘 .3mf，或点击上方选择文件。'));body.append(e)}
  const activeJob=jobs.find(j=>j.id===data.active?.job_id);
  [...(activeJob?[activeJob]:[]),...visible].forEach(job=>{
    const waiting=job.status==='等待',active=data.active?.job_id===job.id,report=setup[job.id]||{},index=jobs.indexOf(job),card=node('article','queue-card'+(active?' active-card':'')+(selected===job.id?' selected':''));
    card.setAttribute('role','listitem');card.dataset.id=job.id;card.tabIndex=0;card.onclick=()=>{selected=job.id;document.querySelectorAll('.queue-card').forEach(c=>c.classList.toggle('selected',c.dataset.id===selected))};card.onkeydown=e=>{if(e.target===card&&['Enter',' '].includes(e.key)){e.preventDefault();card.click()}};
    const handle=button('','drag-handle',e=>e.stopPropagation(),'拖动排序：'+job.name);handle.append(icon('grip'));handle.draggable=waiting;handle.disabled=!waiting;handle.title='按住拖动排序，或用上下方向键';
    handle.onkeydown=e=>{if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();e.stopPropagation();perform(e.key==='ArrowUp'?'up':'down',{id:job.id})}};
    handle.ondragstart=e=>{if(!waiting||busy){e.preventDefault();return}draggingId=job.id;selected=job.id;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-orca-queue-id',job.id);e.dataTransfer.setData('text/plain',job.id);card.classList.add('moving')};handle.ondragend=finishDragging;
    card.ondragover=e=>{if(!draggingId||draggingId===job.id||!waiting||isFileDrag(e))return;e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='move';clearDropHints();const r=card.getBoundingClientRect();card.classList.add(e.clientY<r.top+r.height/2?'drop-before':'drop-after')};
    card.ondrop=e=>{if(!draggingId||!waiting||isFileDrag(e))return;e.preventDefault();e.stopPropagation();const id=draggingId,r=card.getBoundingClientRect(),placement=e.clientY<r.top+r.height/2?'before':'after';draggingId=null;clearDropHints();if(id!==job.id)perform('move',{id,target_id:job.id,placement})};
    card.append(handle,node('span','order',String(index+1)));const thumb=button('','thumb',e=>e.stopPropagation(),'放大预览：'+job.name),src=data.previews?.[job.sha256];
    if(typeof src==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src)){const img=node('img');img.src=src;img.alt=job.name+' 模型缩略图';img.draggable=false;img.onerror=()=>{thumb.replaceChildren(node('span','','暂无预览'));thumb.disabled=true};thumb.append(img);thumb.onclick=e=>{e.stopPropagation();showPreview(src,job.name)}}else{thumb.append(node('span','','暂无预览'));thumb.disabled=true}card.append(thumb);
    const info=node('div','card-info'),heading=node('div','card-heading'),title=node('div','card-title',job.name);title.title=job.name+'\n'+(job.source_path||job.path);heading.append(title,pill(active?(data.phase==='sending'?'发送中':'当前任务'):waiting?(report.ready?'已就绪':report.configured?(report.label||'待检查'):'待配置'):job.status,active||report.ready?'':waiting?'warning':'muted'));info.append(heading);
    const meta=node('div','card-meta');for(const value of ['原盘 '+job.plate,job.object_count+' 个零件',duration(job.duration_s),typeof job.weight_g==='number'?job.weight_g.toFixed(1)+' g':null].filter(Boolean)){if(meta.children.length)meta.append(node('span','meta-separator','·'));meta.append(node('span','',value))}info.append(meta);
    const material=node('div','card-material');for(const f of job.filaments||[])if(validColor(f.color))material.append(swatch(f.color));material.append(node('span','',materialText(job)));info.append(material);
    if(active){const p=node('div','card-progress');p.append(node('span'));p.dataset.jobProgress=job.id;info.append(p,node('div','card-meta active-progress-text','等待实机回报'))}
    else if(waiting&&!report.ready){const reason=report.configured?(report.reason||'耗材配置已保存，装料后刷新检查。'):!Object.keys(job.settings?.mapping||{}).length?'为本盘选择供料方式和耗材槽位。':report.reason||'请检查本盘配置。';info.append(node('div','card-blocker',reason))}
    const actions=node('div','card-actions');
    if(waiting){actions.append(jobButton(report.configured?'耗材设置':'配置耗材','settings',job,report.configured?'':'primary'),jobButton('再加一份','duplicate',job));if(job.object_count>1)actions.append(button('零件预览','',e=>{e.stopPropagation();openObjects(job.id,true)},'查看本盘零件：'+job.name))}
    else if(active){const t=boundDevice(data)?.telemetry||{},hasIdentity=!!Object.keys(data.active.identity||{}).length&&data.active.seen_running&&['RUNNING','PAUSE','PREPARE','SLICING'].includes(t.gcode_state),pause=button(t.gcode_state==='PAUSE'?'继续打印':'暂停打印','',()=>perform(t.gcode_state==='PAUSE'?'resume_print':'pause_print')),skip=button(job.object_count===1?'结束本盘，继续':'跳过零件','',()=>job.object_count===1?confirmControl('end_current'):openObjects());pause.disabled=!hasIdentity;skip.disabled=!hasIdentity;actions.append(pause,skip);if(job.object_count>1){const end=button('结束本盘，继续','',()=>confirmControl('end_current'));end.disabled=!hasIdentity;actions.append(end)}}
    else actions.append(jobButton('再加一份','duplicate',job));
    if(!active&&['等待','已完成','已中止'].includes(job.status)){const remove=jobButton('','remove',job,'icon-button delete-task');remove.title='删除任务';remove.setAttribute('aria-label','删除任务：'+job.name);remove.append(icon('trash'));actions.append(remove)}
    info.append(actions);card.append(info);(active?current:body).append(card);
    const transition=transitions.find(s=>s.after_id===job.id);if(transition&&!active&&queueFilter==='pending'){const step=node('div','swap-step');step.append(icon('swap'),document.createTextNode('两盘之间执行换盘'));step.title='独立发送 '+basename(swapSettings.source_path||swapSettings.path);body.append(step)}
  });updateCardProgress(data);
}
function updateCardProgress(data){const a=data.active,t=boundDevice(data)?.telemetry||{};for(const e of document.querySelectorAll('[data-job-progress]')){const matched=a?.job_id===e.dataset.jobProgress&&Object.keys(a.identity||{}).length,n=matched&&typeof t.mc_percent==='number'?Math.max(0,Math.min(100,t.mc_percent)):0;e.firstChild.style.width=n+'%';const label=e.nextElementSibling;if(label)label.textContent=matched?n+'% · 第 '+(t.layer_num??'—')+' / '+(t.total_layer_num??'—')+' 层':'正在发送，等待打印机启动'}}
function renderSwap(data){const manual=data.plate_mode==='manual',enabled=swapSettings.enabled!==false,valid=!!swapSettings.validated;$('plateHandlingStep').textContent=manual?'手动换板并确认':'独立换盘';setPill('swapBadge',manual?'手动换板':!enabled?'已关闭':valid?'已配置':'待配置',manual?'muted':enabled&&valid?'':'muted');$('swapFileName').textContent=manual?'每盘结束后更换或清空打印板':valid?swapSettings.name||basename(swapSettings.source_path||swapSettings.path):'未选择本机换盘程序';$('swapFileName').title=manual?'':swapSettings.source_path||swapSettings.path||'';$('swapMeta').textContent=manual?'确认新板就位后，继续这台打印机的下一盘。':(swapSettings.nozzle||.4)+' mm'+(swapSettings.motion_only?' · 仅机械换盘':' · 独立换盘任务');$('swapModeSummary').textContent=manual?'本机等待人工确认；其他打印机独立运行。':data.auto_after_swap?'程序完成后，自动开始下一盘。':'每次确认新板就位后，再开始下一盘。';$('openSwap').disabled=!!data.running||!!data.active;if(!swapDirty&&$('swapDialog').open)fillSwapDraft()}

function renderRun(data){const a=data.active,d=boundDevice(data),t=d?.telemetry||{},r=readiness(data),step=nextStep(data),phases={paused:'队列暂停',ready:'准备发送',sending:'正在发送',monitoring:a?.kind==='swap'?'正在换盘':'打印中',stopping:'正在停止',between:'准备换盘',confirm_plate:'等待新板确认',completed:'队列完成',recovery:'等待核对'};
  const monitorStage=a?.monitor?.stage,checking=['syncing','verifying_finish','reconnecting'].includes(monitorStage);if(checking)phases[data.phase]=monitorStage==='reconnecting'?'正在恢复连接':monitorStage==='verifying_finish'?'正在确认完成':'正在核对状态';
  const pausedPrint=data.phase==='monitoring'&&t.gcode_state==='PAUSE';setPill('phaseBadge',pausedPrint?'打印已暂停':phases[data.phase]||'队列暂停',pausedPrint||data.phase==='recovery'||data.phase==='confirm_plate'?'warning':data.running?'':'muted');
  const receipt=connection.commands?.find(x=>x.request_id===a?.request_id),name=a?.kind==='swap'?'独立换盘任务':(data.jobs||[]).find(j=>j.id===a?.job_id)?.name;let text=data.reason||'';
  if(a&&data.phase==='sending')text=(name||'本盘')+' · '+(receipt?.status==='working'?'正在上传切片'+(receipt.progress>0&&receipt.progress<=100?' '+receipt.progress+'%':''):'等待打印机确认启动');
  else if(a&&data.phase==='monitoring')text=(name||'当前任务')+' · '+(t.gcode_state==='PAUSE'?'打印已暂停':(t.mc_percent??'—')+'%');
  else if(!a&&!data.running&&data.phase==='paused')text=step==='device'?'先选择一台在线打印机。':step==='jobs'?'加入单盘切片文件，按顺序准备打印。':step==='materials'?'还有 '+(r.jobs.length-r.configured)+' 盘未配置耗材。':step==='swap'?'先配置两盘之间的换盘文件。':r.ready<r.jobs.length?'配置已保存。装好耗材后，检查并开始。':'任务已准备好，可以检查并开始。';
  if(!a&&!data.running&&step==='materials'&&data.drafts?.length)text=data.drafts.length+' 个文件待配置，确认后加入队列。';
  if(checking)text=data.reason||'正在核对本盘状态，后续任务暂不发送。';
  $('runStatus').textContent=text;$('stopQueue').title='仅停止 '+(d?.name||'当前机器')+'，其他机器继续运行';$('startQueue').hidden=!!a||!!data.running||data.phase==='confirm_plate';$('startQueue').disabled=busy;$('preflight').disabled=busy||!r.jobs.length;$('startQueue').replaceChildren(document.createTextNode({device:'选择打印机',jobs:'加入任务',materials:'配置耗材',swap:'配置换盘',start:'检查并开始'}[step]||'检查并开始'),icon('arrow'));
  $('swapContinue').hidden=data.plate_mode==='manual'||!!a||!!data.running||!data.dirty_plate||!r.jobs.length||data.phase==='confirm_plate';$('swapContinue').disabled=busy;$('confirmPlate').hidden=data.phase!=='confirm_plate';$('stopQueue').hidden=!data.running&&!a;$('resumeMonitor').disabled=!a||!!data.running;$('reconcile').disabled=!!data.running||!a;
  $('recoveryPanel').hidden=!a||!!data.running;if(data.phase==='recovery')$('recoveryPanel').open=true;let review=$('reviewCurrent');if(!review){review=button('核对并恢复','primary',()=>scrollToPanel('recoveryPanel').open=true);review.id='reviewCurrent';$('startQueue').parentElement.append(review)}review.hidden=!a||!!data.running;
  const complete=!!a&&!data.running&&a.kind==='model'&&t.gcode_state==='FINISH'&&t.mc_percent>=100;
  $('completeContinue').hidden=!complete;$('completeContinue').disabled=busy||!deviceReady(d)||(d?.state_age_ms??d?.age_ms??Infinity)>15000||t.subtask_name!==a?.tag;
  if(complete)$('resumeMonitor').disabled=true;
  syncCompletedReview();
}
function applyState(reply){if(!reply.data)return;if(viewQueueId!==null&&reply.queue_id!==undefined&&reply.queue_id!==viewQueueId){for(const d of document.querySelectorAll('dialog[open]'))d.close();editing=null;selected=null;cardsKey='';draggingId=null;noticedImports.clear();startEpoch++}viewQueueId=reply.queue_id??reply.data.device_id;latestReply=reply;connection=reply.connection||{available:false,devices:[]};setup=reply.setup||{};swapSettings=reply.swap_settings||{};transitions=reply.swap_plan||[];renderConnection(reply.data);renderOverview(reply.data);renderSwap(reply.data);renderJobs(reply.data);renderRun(reply.data);renderFleet(reply);if(document.activeElement!==$('auto'))$('auto').checked=!!reply.data.auto_export;$('events').textContent=[...(reply.messages||[])].reverse().join('\n')||'暂无运行记录。';renderImports(reply.data);syncObjectsDialog(reply.data)}
function renderImports(data){renderComponents(latestReply);const drafts=data.drafts||[];$('importPending').hidden=!drafts.length;$('importPendingText').textContent=drafts.length+' 个文件待配置，确认后才会显示在队列。';const fresh=drafts.some(d=>!noticedImports.has(d.id));for(const d of drafts)noticedImports.add(d.id);if(fresh&&!busy&&!editing&&!document.querySelector('dialog[open]'))queueMicrotask(()=>openNextImport())}
function openNextImport(){const draft=latestReply?.data.drafts?.[0];if(draft&&!editing)openSettings(draft.id)}
function showPreview(src,name){$('previewTitle').textContent=name;$('previewImage').src=src;$('previewDialog').showModal()}
function refillIdentity(slot){const type=String(slot?.type||'').trim().toUpperCase(),color=String(slot?.color||'').replace(/^#/,'').toUpperCase();return type&&/^[0-9A-F]{6}([0-9A-F]{2})?$/.test(color)&&!(color.length===8&&color.endsWith('00'))?type+'|'+color+(color.length===6?'FF':''):''}
function renderBackupChoices(f,device){const settings=editing.settings,group=settings.refill?.[f.id],primary=device?.slots.find(s=>s.id===settings.mapping[f.id]),identity=refillIdentity(group)||refillIdentity(primary),box=node('div','backup-choices');
  box.append(node('strong','','跨盘续料备用槽（可选）'),node('small','','主槽不可用时，按勾选顺序使用有料的同类型、同颜色槽。每盘发送前检查；不更改打印机内的自动续料设置。'));
  let count=0;const occupied=new Set(Object.entries(settings.mapping).filter(([id])=>id!==f.id).map(([,slot])=>slot));for(const [id,g] of Object.entries(settings.refill||{}))if(id!==f.id)for(const slot of g.slots||[])occupied.add(slot);
  for(const slot of device?.slots||[]){if(slot.kind!=='ams'||slot.id===primary?.id)continue;const selected=group?.slots?.includes(slot.id),matching=identity&&refillIdentity(slot)===identity,label=node('label','backup-option'),input=node('input');input.type='checkbox';input.dataset.backupSlot=slot.id;input.setAttribute('aria-label','切片耗材 '+f.id+' 备用 '+slot.label);input.checked=!!selected;input.disabled=occupied.has(slot.id)||(!selected&&!matching);label.append(input,swatch(slot.color),document.createTextNode(slot.label+(selected?' · 备用 '+(group.slots.indexOf(slot.id)+1):'')+(slot.present===false?' · 空槽':slot.present!==true?' · 状态待确认':'')+(!matching&&!selected?' · 类型或颜色不匹配':'')));box.append(label);count++;
    input.onchange=()=>{settings.refill||={};const selectedSlots=[...(settings.refill[f.id]?.slots||[])].filter(id=>id!==slot.id);if(input.checked)selectedSlots.push(slot.id);if(selectedSlots.length)settings.refill[f.id]={...(settings.refill[f.id]||{}),slots:selectedSlots};else delete settings.refill[f.id];renderMappings()};
  }if(!count)box.append(node('small','','暂无其他 AMS 槽位。'));return box;
}
function renderMappings(){
  const body=$('materialMappings'),focused=document.activeElement?.dataset.materialSlot,focusedMaterial=document.activeElement?.dataset.materialId;body.replaceChildren();if(!editing)return;
  const {asset,settings}=editing,device=connection.devices.find(d=>d.id===settings.device_id),materials=asset.filaments||[],motion=!!asset.motion_only;$('materialSourceGroup').hidden=motion;$('printOptions').hidden=motion;$('externalReadyLabel').hidden=true;
  if(motion){body.append(node('div','inline-note','默认套件程序仅作机械换盘，无需供料或打印校准。'));$('materialHint').textContent='';return}
  $('materialHint').textContent=settings.source==='external'?'选择实际使用的外挂耗材，可先配置、后装料。':'点击色块选择主槽，再勾选同类型、同颜色的跨盘备用槽。主槽颜色可与切片不同，类型必须一致。';
  if(!materials.length){body.append(node('p','card-blocker','切片缺少耗材登记，请重新导出单盘文件。'));return}
  for(const f of materials){
    const row=node('div','material-row'),title=node('div','material-heading');title.append(swatch(f.color),node('strong','',f.type||'类型未知'),node('small','','切片耗材 '+f.id+' · '+(f.color||'颜色未登记')));row.append(title);
    const choices=node('div','material-slot-choices');choices.setAttribute('role','group');choices.setAttribute('aria-label','切片耗材 '+f.id+' 对应槽位');
    for(const slot of device?.slots||[]){
      if(slot.kind!==settings.source)continue;
      const matching=String(slot.type||'').trim().toUpperCase()===String(f.type||'').trim().toUpperCase(),chosen=settings.mapping[f.id]===slot.id;
      const choice=button('','material-slot'+(chosen?' selected-slot':''),()=>{settings.mapping[f.id]=slot.id;if(settings.refill)delete settings.refill[f.id];renderMappings()},'切片耗材 '+f.id+' 选择 '+slot.label+' · '+(slot.type||'类型未知')+' · '+slotState(slot));
      choice.dataset.materialSlot=slot.id;choice.dataset.materialId=f.id;choice.disabled=!matching;choice.setAttribute('aria-pressed',String(chosen));choice.title=slot.label+' · '+(displayColor(slot.color)||'颜色未知')+(matching?'':' · 与切片耗材类型不一致');
      choice.append(node('span','slot-number',slotShortLabel(slot)),slotColor(slot),node('strong','',slot.type||'类型未知'),node('small','',!matching?'类型不匹配':slotState(slot)),node('span','slot-choice-mark',chosen?'✓ 主槽':'选择'));choices.append(choice);
    }
    if(!choices.children.length)choices.append(node('p','small','没有回报可用的'+(settings.source==='external'?'外挂':'AMS')+'槽位，请刷新设备状态。'));
    row.append(choices);body.append(row);if(settings.source==='ams'&&settings.mapping[f.id])body.append(renderBackupChoices(f,device));
  }
  if(focused){const target=[...body.querySelectorAll('[data-material-slot]')].find(e=>e.dataset.materialSlot===focused&&e.dataset.materialId===focusedMaterial);if(target&&!target.disabled)target.focus({preventScroll:true})}
  updateExternalConfirmation();
}
function updateExternalConfirmation(){if(!editing)return;const s=editing.settings,d=connection.devices.find(d=>d.id===s.device_id),ids=Object.values(s.mapping);$('externalReadyLabel').hidden=s.source!=='external'||!ids.some(id=>d?.slots.find(slot=>slot.id===id)?.present===null)}
function openSettings(id){if(busy)return;const data=latestReply?.data,device=boundDevice(data);if(!device){feedback('请先选择打印机，再配置本盘耗材。',true);focusDevice();return}const draft=data.drafts?.find(d=>d.id===id),asset=id==='__swap__'?swapSettings:draft||data.jobs.find(j=>j.id===id);if(!asset)return;if(!draft&&id!=='__swap__'&&asset.status!=='等待'){feedback('只能修改等待中的任务。',true);return}
  const settings=clone(asset.settings);settings.device_id=data.device_id;
  if(asset.motion_only){settings.source='external';settings.mapping={};settings.options={bed_leveling:false,flow_calibration:false,timelapse:false}}
  else if(!Object.keys(settings.mapping).length&&asset.filaments?.length===1&&!device.slots.some(s=>s.kind==='ams'&&s.present===true)&&device.slots.some(s=>s.kind==='external'))settings.source='external';
  // Suggestions affect this unsaved draft only.
  if(!asset.motion_only)for(const f of asset.filaments||[]){if(settings.mapping[f.id])continue;const slots=device.slots.filter(s=>s.kind===settings.source&&s.type?.trim().toUpperCase()===f.type?.trim().toUpperCase()&&!Object.values(settings.mapping).includes(s.id));if(slots.length===1)settings.mapping[f.id]=slots[0].id}
  const targets=id==='__swap__'?[]:(draft?data.drafts:data.jobs).filter(j=>j.id!==id&&(draft||j.status==='等待')&&materialKey(j)===materialKey(asset)).map(j=>j.id);editing={id,asset,settings,targets,importing:!!draft};
  $('settingsTitle').textContent=draft?'配置耗材后加入队列':id==='__swap__'?'换盘耗材设置':'本盘打印设置';$('savePrintSettings').textContent=draft?'确认加入队列':'保存设置';$('cancelImport').hidden=!draft;$('settingsDevice').textContent='目标打印机：'+device.name+' · '+(MODEL_NAMES[device.model]||device.model)+' · '+(device.nozzle||'—')+' mm';const header=$('settingsAsset');header.replaceChildren();const src=data.previews?.[asset.sha256]||asset.thumbnail;if(typeof src==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src)){const img=node('img');img.src=src;img.alt='本盘模型';header.append(img)}const desc=node('div');desc.append(node('strong','',asset.name||basename(asset.source_path||asset.path)));if(draft){const quantity=node('label','import-copies'),input=node('input');input.id='importCopies';input.type='number';input.min='1';input.max='100';input.step='1';input.value=String(asset.copies);input.setAttribute('aria-label','加入份数');quantity.append(document.createTextNode('加入'),input,document.createTextNode('份'));desc.append(quantity)}desc.append(node('small','',id==='__swap__'?'独立换盘任务':'原盘 '+asset.plate+' · '+asset.object_count+' 个零件'));header.append(desc);
  $('materialSource').value=settings.source;$('externalReady').checked=!!settings.external_ready;$('applyMatching').checked=false;$('applyMatchingLabel').hidden=!targets.length;$('applyMatchingText').textContent=draft?'同时配置其余 '+targets.length+' 个相同耗材的待加入文件':'同时应用到其余 '+targets.length+' 盘相同耗材的等待任务';
  for(const [field,key] of [['bedLeveling','bed_leveling'],['flowCalibration','flow_calibration'],['timelapse','timelapse']]){const input=$(field);input.checked=!!settings.options[key];input.disabled=asset.motion_only||!device.supported_options.includes(key);if(input.disabled)input.checked=false}
  $('settingsError').textContent='';renderMappings();$('settingsDialog').showModal();
}
$('savePrintSettings').onclick=async()=>{if(!editing)return;const draft=editing,element=$('savePrintSettings'),copies=draft.importing?Number($('importCopies').value):null;if(draft.importing&&(!Number.isInteger(copies)||copies<1||copies>100)){$('settingsError').textContent='加入份数须为 1–100 的整数。';$('importCopies').focus();return}element.disabled=true;draft.settings.external_ready=$('externalReady').checked;for(const [field,key] of [['bedLeveling','bed_leveling'],['flowCalibration','flow_calibration'],['timelapse','timelapse']])draft.settings.options[key]=$(field).checked;try{await checkedSend(draft.importing?'commit_import':'save_settings',{id:draft.id,settings:draft.settings,...(draft.importing?{copies}:{}),apply_to:$('applyMatching').checked?draft.targets:[]});if(editing===draft){$('settingsDialog').close();if(draft.importing)openNextImport()}}catch(e){$('settingsError').textContent=e.message}finally{element.disabled=false}};
$('cancelImport').onclick=async()=>{const draft=editing;if(!draft?.importing)return;const b=$('cancelImport');b.disabled=true;try{await checkedSend('discard_import',{id:draft.id});if(editing===draft){$('settingsDialog').close();openNextImport()}}catch(e){$('settingsError').textContent=e.message}finally{b.disabled=false}};
$('materialSource').onchange=()=>{if(editing){editing.settings.source=$('materialSource').value;editing.settings.mapping={};editing.settings.refill={};editing.settings.external_ready=false;$('externalReady').checked=false;renderMappings()}};
$('settingsDialog').addEventListener('close',()=>{editing=null});
function fillSwapDraft(){$('plateMode').value=latestReply?.data.plate_mode||'automatic';$('swapPath').value=swapSettings.source_path||swapSettings.path||'';$('swapNozzle').value=String(swapSettings.nozzle||.4);$('swapEnabled').checked=swapSettings.enabled!==false;$('swapAuto').checked=!!latestReply?.data.auto_after_swap;renderSwapDraftStatus()}
function renderSwapDraftStatus(){const supported=SWAP_MODELS.has(boundDevice()?.model);$('plateMode').querySelector('option[value=automatic]').disabled=!supported;if(!supported)$('plateMode').value='manual';const manual=$('plateMode').value==='manual';$('swapFileFields').hidden=manual;$('swapEnabled').closest('label').hidden=manual;$('swapAuto').closest('label').hidden=manual;$('defaultSwap').disabled=boundDevice()?.model!=='N2S';$('swapStatus').textContent=swapSettings.validated?'已保存并校验：'+(swapSettings.name||basename(swapSettings.path))+(swapSettings.motion_only?'\n仅机械换盘，无需单独装 PLA。':'\n换盘文件使用独立耗材设置。'):'请选择文件并保存校验。';$('swapPrintSettings').hidden=!!swapSettings.motion_only||!swapSettings.validated}
function openSwap(){const data=latestReply?.data;if(data?.running||data?.active){feedback('执行中不能更改换盘设置。',true);return}swapDirty=false;fillSwapDraft();$('swapError').textContent='';$('swapDialog').showModal()}
async function saveSwap(useDefault=false){const b=useDefault?$('defaultSwap'):$('saveSwap');b.disabled=true;$('swapError').textContent='';try{await checkedSend(useDefault?'default_swap':'save_swap',{plate_mode:useDefault?'automatic':$('plateMode').value,path:$('swapPath').value,nozzle:Number($('swapNozzle').value),enabled:$('swapEnabled').checked,automatic:$('swapAuto').checked});swapDirty=false;fillSwapDraft();if(!useDefault)$('swapDialog').close()}catch(e){$('swapError').textContent=e.message}finally{b.disabled=false}}
function startChecks(data){
  const r=readiness(data,startOperation==='swap_first'),d=boundDevice(data),fresh=deviceReady(d),state=d?.telemetry?.gcode_state,stateFresh=(d?.state_age_ms??d?.age_ms??Infinity)<=15000,idle=fresh&&stateFresh&&READY_STATES.has(state),fault=deviceFaultText(d);
  let idleReason='';
  if(!fresh||!stateFresh)idleReason='设备连接或状态回报未就绪，请刷新本机状态后重新检查。';
  else if(!READY_STATES.has(state))idleReason=['RUNNING','PREPARE','SLICING','PAUSE'].includes(state)?'设备回报仍有运行中或暂停的任务（'+state+'），请先在设备或 Handy 核对。':'设备状态为 '+(state||'未知')+'，暂未确认空闲，请刷新后核对。';
  return [['当前打印机在线且空闲',idle,idleReason],['设备错误与告警检查',!fault,fault+'。请在 Orca 的“设备 → 助手(HMS)”或 Handy 查看并处理。'],['本轮 '+r.jobs.length+' 盘耗材已就绪',r.jobs.length>0&&r.ready===r.jobs.length,r.ready<r.jobs.length?'请装好耗材并完成每盘配置，再重新检查。':''],[data.plate_mode==='manual'?'本机使用手动换板':'本机换盘任务已配置',r.swap,r.swap?'':'请先保存对应喷嘴的换盘文件。']];
}
function renderStartChecklist(extra=''){const body=$('startChecklist');body.replaceChildren();if(startOperation==='reconcile'){body.append(node('p','small','仅记录核对结果，不向打印机发送停止或打印指令。'));return}for(const [text,good,reason] of startChecks(latestReply?.data||{})){const row=node('div',good?'':'bad'),textNode=node('div');row.append(icon(good?'check':'info'));textNode.append(document.createTextNode(text));if(!good&&reason)textNode.append(node('p','small',reason));row.append(textNode);body.append(row)}if(extra)body.append(node('p','small',extra))}
function updateStartButton(){const ack=startOperation==='reconcile'?$('checkedPending').checked:startOperation==='swap_first'?$('swapReady').checked:$('bedClear').checked;$('confirmStart').disabled=startChecking||!ack||(startOperation!=='reconcile'&&!startPassed)}
async function checkStart(){if(startOperation==='reconcile'){startPassed=true;renderStartChecklist();updateStartButton();return}const epoch=++startEpoch;startChecking=true;startPassed=false;updateStartButton();$('startError').textContent='';renderStartChecklist('正在核对文件、设备和耗材…');try{await checkedSend('preflight',{for_start:true,swap_first:startOperation==='swap_first'});if(epoch!==startEpoch||!$('startDialog').open)return;startPassed=true;renderStartChecklist('文件、设备与逐盘设置检查通过。')}catch(e){if(epoch!==startEpoch||!$('startDialog').open)return;$('startError').textContent=e.message;renderStartChecklist()}finally{if(epoch===startEpoch){startChecking=false;updateStartButton()}}}
function openStart(operation){if(busy)return;startOperation=operation;startPassed=false;startChecking=false;$('bedClear').checked=false;$('swapReady').checked=false;$('checkedPending').checked=false;$('startError').textContent='';const reconcile=operation==='reconcile',swapFirst=operation==='swap_first',jobs=pendingJobs();$('startDescription').dataset.deviceId=latestReply?.data.device_id||'';$('startTitle').textContent=reconcile?'确认当前任务已结束':swapFirst?'换盘后继续队列':'开始前检查';$('startDescription').textContent=(boundDevice()?.name||'当前机器')+' · '+(reconcile?'请先核对打印机和 Handy，防止已有任务稍后启动。':swapFirst?'先运行独立换盘文件，再开始下一盘。':'检查通过并确认打印板就绪后，才会发送打印。');$('bedClearGroup').hidden=swapFirst;$('bedClearGroup').querySelector('span').textContent=reconcile?'当前已装好空白打印板（未勾选则保留待换盘状态）':latestReply?.data.plate_mode==='manual'?'已安装空白打印板，打印区域已清空':'已安装空白打印板，换盘机构及备板已就绪';$('swapReadyGroup').hidden=!swapFirst;$('checkedPendingGroup').hidden=!reconcile;$('recheckStart').hidden=reconcile;$('confirmStart').textContent=reconcile?'记录已结束':swapFirst?'确认换盘并继续':'确认并开始';const summary=$('startSummary');summary.replaceChildren();if(!reconcile){const a=node('div'),b=node('div');a.append(node('strong','',jobs.length+' 盘任务'),node('small','',boundDevice()?.name||'打印机未绑定'));b.append(node('strong','',duration(jobs.reduce((s,j)=>s+(j.duration_s||0),0))),node('small','','切片预计用时，不含调平与换盘'));summary.append(a,b)}summary.hidden=reconcile;$('startDialog').showModal();checkStart()}
$('startDialog').addEventListener('close',()=>{startEpoch++;startChecking=false});
$('confirmStart').onclick=async()=>{const b=$('confirmStart');if(b.disabled)return;b.disabled=true;const epoch=++startEpoch;try{await checkedSend(startOperation==='reconcile'?'reconcile':'start',{bed_clear:$('bedClear').checked,swap_first:startOperation==='swap_first',checked_pending:$('checkedPending').checked});if(epoch===startEpoch)$('startDialog').close()}catch(e){$('startError').textContent=e.message;startPassed=false}finally{updateStartButton()}};
function confirmControl(action){actionIntent=action;$('actionError').textContent='';const continuing=action==='end_current',name=boundDevice()?.name||'当前机器',manual=latestReply?.data.plate_mode==='manual';$('actionTitle').textContent=name+' · '+(continuing?'结束本盘，继续队列':'停止本机打印并暂停队列');$('actionDescription').textContent=continuing?'将结束 '+name+' 的当前盘。'+(pendingJobs().length?(manual?'随后等待手动换板，确认后继续下一盘。':'随后按本机换盘设置继续下一盘。'):'没有后续任务，保留最后一盘。')+'其他打印机继续各自运行。':'将停止 '+name+' 的当前打印，并暂停本机后续队列。其他打印机继续各自运行。';$('confirmAction').textContent=continuing?'结束本盘并继续':'停止并暂停队列';$('actionDialog').showModal()}
function syncCompletedReview(){
  const ctx=completionAttempt;if(!ctx)return;const a=latestReply?.data.active,d=boundDevice(),t=d?.telemetry||{};
  const current=a?.request_id===ctx.request_id&&viewQueueId===ctx.queue_id;
  const ready=current&&!latestReply?.data.running&&deviceReady(d)&&(d.state_age_ms??d.age_ms)<=15000&&t.gcode_state==='FINISH'&&t.mc_percent>=100&&t.subtask_name===ctx.tag&&!deviceFaultText(d);
  $('confirmComplete').disabled=ctx.working||ctx.checking||!ctx.passed||!$('completeConfirmed').checked||!ready;
  $('recheckComplete').disabled=ctx.working||ctx.checking;
  if(!current&&$('completeDialog').open){ctx.passed=false;$('completeError').textContent='当前任务已变化，请关闭后重新核对。'}
}
async function checkCompletedReview(){
  const ctx=completionAttempt;if(!ctx||ctx.working||ctx.checking)return;ctx.checking=true;ctx.passed=false;$('completeError').textContent='';$('completeCheck').textContent='正在核对本盘完成状态、后续文件与换盘设置…';syncCompletedReview();
  try{await checkedSend('preflight',{completion_review:true,attempt_id:ctx.request_id});if(completionAttempt!==ctx)return;ctx.passed=true;$('completeCheck').textContent='本盘完成状态与后续任务检查通过。'}
  catch(e){if(completionAttempt===ctx){$('completeError').textContent=e.message;$('completeCheck').textContent='尚未通过检查。'}}
  finally{if(completionAttempt===ctx){ctx.checking=false;syncCompletedReview()}}
}
function openCompletedReview(){
  const data=latestReply?.data,a=data?.active;if(!a||busy)return;
  completionAttempt={request_id:a.request_id,queue_id:viewQueueId,tag:a.tag,passed:false,checking:false,working:false};
  const manual=data.plate_mode==='manual',next=pendingJobs().length>0;
  $('completeDevice').textContent=boundDevice()?.name||'当前打印机';$('completeAsset').textContent=data.jobs.find(j=>j.id===a.job_id)?.name||'当前盘';
  $('completeDescription').textContent='设备已回报本盘成功结束。确认后将本盘记为已完成，'+(!next?'本机队列结束，保留最后一盘。':manual?'等待手动更换打印板，再继续下一盘。':'按本机设置运行独立换盘，再继续下一盘。')+'不会重发本盘文件。';
  $('completeConfirmationText').textContent='已确认本盘打印成功，Handy 没有待启动任务'+(next&&!manual?'，换盘机构和备板已就绪':'');
  $('completeConfirmed').checked=false;$('completeError').textContent='';$('completeDialog').showModal();checkCompletedReview();
}
$('completeDialog').addEventListener('close',()=>{completionAttempt=null});
$('closeComplete').onclick=()=>$('completeDialog').close();$('recheckComplete').onclick=checkCompletedReview;$('completeConfirmed').onchange=syncCompletedReview;
$('confirmComplete').onclick=async()=>{const ctx=completionAttempt;if(!ctx||$('confirmComplete').disabled)return;ctx.working=true;syncCompletedReview();try{await checkedSend('complete_continue',{attempt_id:ctx.request_id,confirmed:$('completeConfirmed').checked});if(completionAttempt===ctx)$('completeDialog').close()}catch(e){if(completionAttempt===ctx){$('completeError').textContent=e.message;ctx.passed=false}}finally{if(completionAttempt===ctx){ctx.working=false;syncCompletedReview()}}};
$('confirmAction').onclick=async()=>{const b=$('confirmAction');b.disabled=true;try{await checkedSend(actionIntent);$('actionDialog').close()}catch(e){$('actionError').textContent=e.message}finally{b.disabled=false}};
function svgElement(tag,attributes={}){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))e.setAttribute(key,String(value));return e}
function objectAttempt(data){const a=data?.active;return JSON.stringify([data?.device_id,a?.job_id,a?.request_id,a?.tag,a?.identity])}
function updateObjectHover(id){if(!objectsState)return;objectsState.hover=id;syncObjectUI()}
function toggleObject(id){const ctx=objectsState;if(!ctx||ctx.submitting||ctx.done.has(id)||ctx.pending.has(id))return;if(ctx.selected.has(id))ctx.selected.delete(id);else ctx.selected.add(id);syncObjectUI()}
function syncObjectUI(){
  const ctx=objectsState;if(!ctx)return;
  const selectable=ctx.job.objects.filter(o=>!ctx.done.has(String(o.id))&&!ctx.pending.has(String(o.id))),selected=selectable.filter(o=>ctx.selected.has(String(o.id))).length;
  for(const row of $('objectsList').children){const id=row.dataset.objectId,input=row.querySelector('input'),done=ctx.done.has(id),pending=ctx.pending.has(id);input.checked=done||pending||ctx.selected.has(id);input.disabled=done||pending||ctx.submitting;row.classList.toggle('selected-object',ctx.selected.has(id)&&!done&&!pending);row.classList.toggle('hover-object',ctx.hover===id);row.classList.toggle('skipped-object',done);const badge=row.querySelector('.object-state');badge.textContent=done?'已跳过':pending?'待设备确认':ctx.selected.has(id)?(ctx.readOnly?'已选择':'待跳过'):'';badge.hidden=!badge.textContent}
  for(const hit of $('objectsPreview').querySelectorAll('.object-hit')){const id=hit.dataset.objectId,blocked=ctx.done.has(id)||ctx.pending.has(id);hit.classList.toggle('selected-object',ctx.selected.has(id)&&!blocked);hit.classList.toggle('hover-object',ctx.hover===id);hit.classList.toggle('skipped-object',blocked);hit.setAttribute('aria-pressed',String(ctx.selected.has(id)||blocked));hit.setAttribute('aria-disabled',String(blocked||ctx.submitting))}
  $('objectsSelected').textContent=selected+' / '+selectable.length+' 已选';$('objectsAlreadySkipped').textContent=(ctx.done.size?'已跳过 '+ctx.done.size+' 个':'')+(ctx.pending.size?' · '+ctx.pending.size+' 个待确认':'');
  const all=$('objectsSelectAll');all.checked=!!selectable.length&&selected===selectable.length;all.indeterminate=selected>0&&selected<selectable.length;all.disabled=!selectable.length||ctx.submitting;
  const ending=!!selected&&selected===selectable.length,device=boundDevice(),canControl=deviceReady(device)&&(device.state_age_ms??device.age_ms)<=15000&&!!Object.keys(latestReply?.data.active?.identity||{}).length;const confirm=$('confirmSkip');confirm.hidden=ctx.readOnly;confirm.disabled=ctx.submitting||!selected||!!ctx.pending.size||!ctx.readOnly&&!canControl||!ctx.job.label_markers&&!ending;confirm.textContent=ending?'结束本盘，继续队列':'跳过所选零件'+(selected?'（'+selected+'）':'');confirm.classList.toggle('danger-solid',ending);confirm.classList.toggle('primary',!ending);
  $('objectsReadOnly').hidden=!ctx.readOnly;
  $('objectsConsequence').textContent=ctx.readOnly?'当前为零件预览，选择不会发送到打印机。':!canControl?'设备状态或当前任务身份未就绪，可预览选择，恢复连接并核对后才能提交跳过。':ending?'已选中全部剩余零件。确认将结束当前盘，'+(!pendingJobs().length?'本机没有后续任务，最后一盘保留。':latestReply?.data.plate_mode==='manual'?'等待手动换板后继续本机队列。':'按本机换盘设置继续下一盘。'):ctx.pending.size?'已有跳过指令等待设备确认，暂不能再次提交。':!ctx.job.label_markers?'切片缺少原生零件跳过标记，仅支持选中全部剩余零件后结束本盘。':selected?'仅跳过选中零件，其他零件继续打印。':'选择需要跳过的零件，确认前不会发送操作。';
}
function renderObjectRows(){
  const ctx=objectsState,body=$('objectsList');body.replaceChildren();if(!ctx)return;
  ctx.job.objects.forEach((object,index)=>{const id=String(object.id),row=node('div','object-row'),label=node('label'),input=node('input');row.dataset.objectId=id;input.type='checkbox';input.value=id;input.setAttribute('aria-label','选择零件 '+(index+1)+'：'+object.name);input.onchange=()=>toggleObject(id);const thumb=node('span','object-thumb');thumb.dataset.thumbObject=id;thumb.append(icon('stack'));label.append(input,thumb,node('span','object-list-name',(index+1)+'. '+object.name));const badge=pill('','muted');badge.classList.add('object-state');row.append(label,badge);row.onmouseenter=()=>updateObjectHover(id);row.onmouseleave=()=>updateObjectHover(null);row.onfocusin=()=>updateObjectHover(id);row.onfocusout=()=>updateObjectHover(null);body.append(row)});
  $('objectsListTitle').textContent='本盘零件（'+ctx.job.objects.length+'）';syncObjectUI();
}
function objectImage(top,width,height){return svgElement('image',{href:top,x:0,y:0,width,height,'pointer-events':'none'})}
function renderObjectPreview(preview){
  const ctx=objectsState;if(!ctx)return;ctx.preview=preview;const body=$('objectsPreview');body.replaceChildren();$('objectsPreviewNote').textContent=preview.note||'可通过下方列表选择零件。';
  const w=preview.width,h=preview.height,validSize=Number.isInteger(w)&&Number.isInteger(h)&&w>0&&h>0&&w<=1024&&h<=1024,top=preview.top;
  const validTop=typeof top==='string'&&top.length<=700000&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(top);
  const ids=new Set(ctx.job.objects.map(o=>String(o.id))),seen=new Set(),regions=(preview.regions||[]);
  const valid=preview.available===true&&validSize&&validTop&&regions.length===ids.size&&regions.every(r=>{const id=String(r.id);if(!ids.has(id)||seen.has(id)||typeof r.path!=='string'||r.path.length>1000000||!/^([Mhvz0-9 .-])+$/.test(r.path)||!Array.isArray(r.box)||r.box.length!==4||!r.box.every(Number.isFinite)||r.box[0]<0||r.box[1]<0||r.box[2]>w||r.box[3]>h||r.box[0]>=r.box[2]||r.box[1]>=r.box[3])return false;seen.add(id);return true});
  $('objectsFit').disabled=!valid;
  if(!validSize||!validTop){body.append(node('div','object-preview-empty','此文件暂无可用俯视图，请使用下方零件列表。'));return}
  const svg=svgElement('svg',{viewBox:'0 0 '+w+' '+h,role:'group','aria-label':valid?'打印板俯视图，可点击零件或编号选择':'打印板俯视图，使用下方列表选择'});svg.append(svgElement('rect',{x:1,y:1,width:w-2,height:h-2,rx:12,class:'object-bed'}),objectImage(top,w,h));body.append(svg);ctx.svg=svg;
  if(!valid){if(preview.available)$('objectsPreviewNote').textContent='位置映射未能核对，请使用下方列表。';return}
  ctx.regions=new Map(regions.map(r=>[String(r.id),r]));
  ctx.job.objects.forEach((object,index)=>{const id=String(object.id),region=ctx.regions.get(id),group=svgElement('g',{class:'object-hit','data-object-id':id,role:'button',tabindex:0,'aria-label':'选择零件 '+(index+1)+'：'+object.name,'aria-pressed':'false'}),title=svgElement('title');title.textContent=(index+1)+'. '+object.name;const shape=svgElement('path',{d:region.path,class:'object-shape'}),x=Math.min(w-12,region.box[2]+10),y=Math.max(12,region.box[1]),pin=svgElement('g',{class:'object-pin',transform:'translate('+x+' '+y+')'}),circle=svgElement('circle',{r:9}),number=svgElement('text',{'text-anchor':'middle','dominant-baseline':'central'});number.textContent=String(index+1);pin.append(circle,number);group.append(title,shape,pin);group.onclick=()=>toggleObject(id);group.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();toggleObject(id)}};group.onmouseenter=()=>updateObjectHover(id);group.onmouseleave=()=>updateObjectHover(null);group.onfocus=()=>updateObjectHover(id);group.onblur=()=>updateObjectHover(null);svg.append(group);
    const thumb=[...$('objectsList').querySelectorAll('[data-thumb-object]')].find(e=>e.dataset.thumbObject===id);if(thumb){const pad=3,box=region.box,thumbSvg=svgElement('svg',{viewBox:[box[0]-pad,box[1]-pad,box[2]-box[0]+pad*2,box[3]-box[1]+pad*2].join(' '),'aria-hidden':'true'}),defs=svgElement('defs'),clip=svgElement('clipPath',{id:'objectClip'+ctx.serial+'_'+index,clipPathUnits:'userSpaceOnUse'});clip.append(svgElement('path',{d:region.path}));defs.append(clip);const img=objectImage(top,w,h);img.setAttribute('clip-path','url(#objectClip'+ctx.serial+'_'+index+')');thumbSvg.append(defs,img);thumb.replaceChildren(thumbSvg)}
  });syncObjectUI();
}
function setObjectViewport(fit){const ctx=objectsState;if(!ctx?.svg||!ctx.preview)return;const {width:w,height:h}=ctx.preview;if(!fit||!ctx.regions?.size){ctx.svg.setAttribute('viewBox','0 0 '+w+' '+h);return}const boxes=[...ctx.regions.values()].map(r=>r.box),x1=Math.min(...boxes.map(b=>b[0])),y1=Math.min(...boxes.map(b=>b[1])),x2=Math.max(...boxes.map(b=>b[2])),y2=Math.max(...boxes.map(b=>b[3])),side=Math.min(Math.max(x2-x1,y2-y1)+48,Math.max(w,h)),x=Math.max(0,Math.min(w-side,(x1+x2-side)/2)),y=Math.max(0,Math.min(h-side,(y1+y2-side)/2));ctx.svg.setAttribute('viewBox',[x,y,side,side].join(' '))}
function syncObjectsDialog(data){
  const ctx=objectsState;if(!ctx||!$('objectsDialog').open)return;
  const job=data.jobs?.find(j=>j.id===ctx.job.id);if(viewQueueId!==ctx.queueId||!job||!ctx.readOnly&&objectAttempt(data)!==ctx.attempt){$('objectsDialog').close();feedback('当前任务已变化，请重新打开本盘零件列表。');return}
  const a=data.active,t=boundDevice(data)?.telemetry||{};ctx.done=new Set(ctx.readOnly?[]:[...(a?.skipped||[]),...(t.s_obj||[])].map(String).filter(id=>ctx.ids.has(id)));ctx.pending=new Set(ctx.readOnly?[]:(a?.pending_skip?.objects||[]).map(String).filter(id=>ctx.ids.has(id)&&!ctx.done.has(id)));for(const id of [...ctx.done,...ctx.pending])ctx.selected.delete(id);syncObjectUI();
}
async function openObjects(jobId=null,readOnly=false){
  const data=latestReply?.data,job=data?.jobs.find(j=>j.id===(jobId||data.active?.job_id));if(!job)return;if(!readOnly&&job.object_count===1)return confirmControl('end_current');
  const ctx={serial:++objectsSerial,queueId:viewQueueId,attempt:objectAttempt(data),job,ids:new Set(job.objects.map(o=>String(o.id))),done:new Set(),pending:new Set(),selected:new Set(),readOnly,submitting:false,hover:null};objectsState=ctx;
  $('objectsTitle').textContent=readOnly?'本盘零件预览':'跳过本盘零件';$('objectsDescription').textContent=(boundDevice()?.name||'当前机器')+' · '+job.name;$('objectsError').textContent='';$('objectsPreviewNote').textContent='正在读取本盘俯视图与零件位置…';$('objectsPreview').replaceChildren(node('div','object-preview-empty','正在读取零件预览…'));$('objectsFit').disabled=true;renderObjectRows();$('objectsDialog').showModal();syncObjectsDialog(data);
  try{const reply=await checkedSend('object_preview',{id:job.id});if(objectsState!==ctx||!$('objectsDialog').open)return;if(reply.job_id!==job.id||reply.queue_id!==ctx.queueId)throw Error('零件预览归属不匹配。');renderObjectPreview(reply.preview||{})}catch(e){if(objectsState!==ctx)return;$('objectsPreview').replaceChildren(node('div','object-preview-empty','预览暂不可用，可使用下方列表。'));$('objectsPreviewNote').textContent=e.message}
}
$('objectsSelectAll').onchange=()=>{const ctx=objectsState;if(!ctx)return;for(const o of ctx.job.objects){const id=String(o.id);if(!ctx.done.has(id)&&!ctx.pending.has(id)){if($('objectsSelectAll').checked)ctx.selected.add(id);else ctx.selected.delete(id)}}syncObjectUI()};
$('objectsWhole').onclick=()=>setObjectViewport(false);$('objectsFit').onclick=()=>setObjectViewport(true);
$('objectsDialog').addEventListener('close',()=>{objectsState=null});
$('confirmSkip').onclick=async()=>{const ctx=objectsState;if(!ctx||ctx.readOnly||ctx.submitting||$('confirmSkip').disabled)return;const objects=[...ctx.selected].filter(id=>!ctx.done.has(id)&&!ctx.pending.has(id)).map(Number);if(!objects.length)return;ctx.submitting=true;syncObjectUI();try{await checkedSend('skip_objects',{objects});if(objectsState===ctx)$('objectsDialog').close()}catch(e){if(objectsState===ctx)$('objectsError').textContent=e.message}finally{if(objectsState===ctx){ctx.submitting=false;syncObjectUI()}}};
function encodeChunk(bytes){let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text)}
async function importFiles(files){
  if(busy){feedback('已有文件正在导入，请稍后再拖入。');return}
  if(!window.orca){feedback('请在 Orca 的打印队列插件页面拖入文件。',true);return}
  if(!boundDevice()){focusDevice();return}
  const list=Array.from(files);if(!list.length)return;
  if(list.length>20){feedback('每次最多导入 20 个文件。',true);return}
  const copies=1;
  busy=true;$('dropZone').setAttribute('aria-disabled','true');$('uploadStatus').hidden=false;$('add').disabled=true;$('uploadProgress').hidden=false;$('uploadProgress').value=0;
  const errors=[];let succeeded=0;
  try{
    for(let n=0;n<list.length;n++){
      const file=list[n];let token=null;
      try{
        if(!file.name.toLowerCase().endsWith('.3mf'))throw new Error('只接受单盘切片 .3mf');
        if(file.size<=0||file.size>100*1024*1024)throw new Error('文件大小须为 0–100 MB，且不能是空文件');
        $('uploadStatus').textContent='正在导入 '+(n+1)+' / '+list.length+'：'+file.name;
        const begin=await checkedSend('upload_begin',{name:file.name,size:file.size,copies});token=begin.upload.token;
        const chunkSize=begin.upload.chunk_size;
        for(let offset=0,seq=0;offset<file.size;offset+=chunkSize,seq++){
          const bytes=new Uint8Array(await file.slice(offset,offset+chunkSize).arrayBuffer());
          await checkedSend('upload_chunk',{token,seq,content:encodeChunk(bytes)});
          $('uploadProgress').value=((n+Math.min(1,(offset+bytes.length)/file.size))/list.length)*100;
        }
        await checkedSend('upload_end',{token});token=null;succeeded++;
      }catch(error){
        errors.push(file.name+'：'+error.message);
        if(token)await send('upload_abort',{token});
      }
    }
  }finally{
    busy=false;$('dropZone').removeAttribute('aria-disabled');$('add').disabled=false;$('uploadProgress').value=100;$('fileInput').value='';
    $('uploadStatus').textContent='已读取 '+succeeded+' 个文件'+(errors.length?'，'+errors.length+' 个未导入':'')+'。配置耗材并确认后加入队列。';
    feedback(errors.length?errors.join('\n'):'文件已读取，请配置耗材并确认加入队列。',errors.length>0);
    if(latestReply)applyState(latestReply);send('refresh');
  }
}


const zone=$('dropZone'),picker=$('fileInput');
zone.onclick=()=>{if(!busy)picker.click()};zone.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();if(!busy)picker.click()}};picker.onchange=()=>importFiles(picker.files);
document.addEventListener('dragover',e=>{if(isFileDrag(e)){e.preventDefault();e.dataTransfer.dropEffect=busy?'none':'copy';zone.classList.add('drag-over');pointerDragging=true}});
document.addEventListener('dragleave',e=>{if(!e.relatedTarget){zone.classList.remove('drag-over');pointerDragging=false}});
document.addEventListener('drop',e=>{if(!isFileDrag(e))return;e.preventDefault();zone.classList.remove('drag-over');pointerDragging=false;importFiles(e.dataTransfer.files)});
document.addEventListener('dragend',()=>{zone.classList.remove('drag-over');pointerDragging=false});
document.addEventListener('click',e=>{if(!e.target.closest('#importOptions'))$('importOptions').open=false});
$('quickAdd').onclick=()=>guide('jobs');
$('openConnection').onclick=()=>{renderComponents(latestReply);$('connectionDialog').showModal()};
$('closeConnection').onclick=()=>$('connectionDialog').close();
$('connectionDownloadUrl').onclick=()=>$('connectionDownloadUrl').select();
for(const [id,dialog] of [['closeSettings','settingsDialog'],['closeSwap','swapDialog'],['cancelSwap','swapDialog'],['closeStart','startDialog'],['closeObjects','objectsDialog'],['closeAction','actionDialog'],['cancelAction','actionDialog'],['closePreview','previewDialog'],['closeHelp','helpDialog']])$(id).onclick=()=>$(dialog).close();
$('pendingTab').onclick=()=>{queueFilter='pending';renderJobs(latestReply?.data||{jobs:[]})};$('historyTab').onclick=()=>{queueFilter='history';renderJobs(latestReply?.data||{jobs:[]})};
$('configureImports').onclick=openNextImport;
$('openHelp').onclick=()=>$('helpDialog').showModal();$('openSwap').onclick=openSwap;$('saveSwap').onclick=()=>saveSwap();$('defaultSwap').onclick=()=>saveSwap(true);
$('checkSwap').onclick=async()=>{try{await checkedSend('check_swap');$('swapStatus').textContent='已保存的换盘文件校验通过。'+(swapDirty?' 当前修改尚未保存。':'')}catch(e){$('swapError').textContent=e.message}};
$('swapPrintSettings').onclick=()=>openSettings('__swap__');for(const id of ['swapPath','swapNozzle','swapEnabled','swapAuto','plateMode'])$(id).oninput=()=>{swapDirty=true;renderSwapDraftStatus()};
$('add').onclick=async()=>{if(!boundDevice())return focusDevice();if(!busy)await perform('add',{path:$('path').value,copies:1},$('add'))};
$('auto').onchange=()=>perform('auto',{enabled:$('auto').checked});$('refresh').onclick=()=>perform('refresh',{},$('refresh'));
$('refreshDevices').onclick=()=>perform('refresh_devices',{device_id:latestReply?.data.device_id||''},$('refreshDevices'));
$('preflight').onclick=async()=>{const b=$('preflight');b.disabled=true;$('preflightResult').textContent='正在检查…';try{await checkedSend('preflight');$('preflightResult').textContent='文件与耗材检查通过。'}catch(e){$('preflightResult').textContent=e.message}finally{b.disabled=false}};
$('startQueue').onclick=()=>guide();$('swapContinue').onclick=()=>openStart('swap_first');$('confirmPlate').onclick=()=>perform('confirm_plate',{},$('confirmPlate'));
$('completeContinue').onclick=openCompletedReview;
$('stopQueue').onclick=()=>confirmControl('stop_queue');$('resumeMonitor').onclick=()=>perform('resume_monitor',{},$('resumeMonitor'));$('reconcile').onclick=()=>openStart('reconcile');$('exportReport').onclick=()=>perform('export_report',{},$('exportReport'));
$('recheckStart').onclick=checkStart;for(const id of ['bedClear','swapReady','checkedPending'])$(id).onchange=updateStartButton;
if(window.orca){
  orca.onMessage(reply=>{const pending=pendingRequests.get(reply.request_id);if(pending){clearTimeout(pending.timer);pendingRequests.delete(reply.request_id);pending.resolve(reply)}if(reply.queue_id!==undefined&&viewQueueId!==null&&reply.queue_id!==viewQueueId&&!['select_queue','bind_device'].includes(pending?.action))return;if(reply.success){if(reply.data){latestReply=reply;if(!busy&&!draggingId)applyState(reply)}if(reply.note&&!busy&&reply.action!=='preflight')feedback(reply.note)}else if(!busy&&!['save_settings','save_swap','default_swap','preflight','start','reconcile','end_current','stop_queue','skip_objects'].includes(pending?.action))feedback(reply.note||'操作失败',true)});
  send('refresh');setInterval(()=>{if(!busy&&!draggingId&&!pointerDragging&&!pendingRequests.size)send('refresh')},3000);
}else{applyState({data:{jobs:[],device_id:'',phase:'paused'},connection:{available:false,devices:[],reason:'请在 Orca 的“打印队列”页使用。'},swap_settings:{enabled:true,nozzle:.4}})}
