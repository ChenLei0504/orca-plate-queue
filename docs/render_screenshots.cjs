/* Render the real queue page with synthetic documentation data only. */
const fs=require('node:fs'),path=require('node:path');
const root=process.cwd();
const {multiFixture,amsFixture}=require(path.join(root,'test_page.cjs'));
const out=path.join(root,'verification/readme');fs.mkdirSync(out,{recursive:true});
for(const language of ['zh-CN','en'])for(const scene of ['overview','materials','objects','swap','connection']){
 const s=multiFixture(),ams=amsFixture();
 s.version='0.7.8';s.build_id='20261102.5';s.language=language;s.language_revision=0;s.connection.material_mapping_ready=true;
 s.data.previews={};s.default_swap_available=false;s.queue_id='fixture-a1';
 s.data.plate_mode='automatic';s.data.auto_after_swap=false;s.data.active.request_id='demo-request';s.data.active.identity={subtask_id:'demo-task'};
 const d=s.connection.devices[0];d.name='A1 · 示例工作台';d.monitor_epoch='documentation-demo';d.state_age_ms=0;d.state_event=42;d.filament_at_toolhead=1;
 d.telemetry={gcode_state:'RUNNING',mc_percent:42,layer_num:86,total_layer_num:204,nozzle_temper:225,bed_temper:65,print_error:0,subtask_id:'demo-task',subtask_name:s.data.active.tag,s_obj:[]};
 d.slots=ams.connection.devices[0].slots;
 d.slots[0].color='#EBE6E6FF';d.slots[1].color='#EBE6E6FF';d.slots[2].color='#50B9CDFF';d.slots[3].color='#222A2EFF';
 d.slots.push({id:'external',label:'外挂耗材',kind:'external',type:'PETG',present:false,color:'#BDBEBDFF'});
 s.connection.devices[1].name='P1S · 示例工作台';
 s.fleet[0].name=d.name;s.fleet[0].pending=2;s.fleet[0].completed=3;s.fleet[1].name=s.connection.devices[1].name;
 s.data.jobs[0].name='定位环_4件.gcode.3mf';s.data.jobs[0].duration_s=2700;s.data.jobs[0].weight_g=18.6;
 s.data.jobs[0].objects=[1419,1420,1421,1422].map((id,i)=>({id:String(id),name:'定位环 '+(i+1)}));s.data.jobs[0].object_count=4;
 s.data.jobs[1].name='定位环_蓝色4件.gcode.3mf';s.data.jobs[1].objects=structuredClone(s.data.jobs[0].objects);s.data.jobs[1].object_count=4;s.data.jobs[1].duration_s=3900;s.data.jobs[1].weight_g=32.4;
 const third=structuredClone(s.data.jobs[1]);third.id='job3';third.name='定位环_备用4件.gcode.3mf';third.sha256='hash3';third.duration_s=1680;third.weight_g=12.8;s.data.jobs.push(third);
 for(const job of s.data.jobs){job.settings.mapping={'9':'ams/0/tray/0'};s.setup[job.id]={configured:true,ready:true}}
 s.swap_plan=[{after_id:'job1',before_id:'job2',file:'example/swap.3mf',nozzle:.4},{after_id:'job2',before_id:'job3',file:'example/swap.3mf',nozzle:.4}];
 s.swap_settings={...s.swap_settings,name:'A1_示例换盘程序.gcode.3mf',source_path:'C:/PlateQueue/example/plate-swap.gcode.3mf'};
 if(['materials','swap','connection'].includes(scene)){
  s.data.running=false;s.data.active=null;s.data.phase='paused';s.data.jobs[0].status='等待';d.telemetry.gcode_state='IDLE';d.telemetry.mc_percent=0;d.telemetry.nozzle_temper=24;d.telemetry.bed_temper=25;s.fleet[0].running=false;s.fleet[0].active=false;
 }
 if(scene==='materials'){
  const draft=structuredClone(s.data.jobs[1]);draft.id='draft-example';draft.copies=3;delete draft.status;s.data.drafts=[draft];
 }
 if(language==='en'){
  d.name='A1 · Demo Bench';s.connection.devices[1].name='P1S · Demo Bench';s.fleet[0].name=d.name;s.fleet[1].name=s.connection.devices[1].name;
  s.data.jobs.forEach((job,i)=>{job.name=['Ring_Set_4.gcode.3mf','Blue_Rings_4.gcode.3mf','Spare_Rings_4.gcode.3mf'][i];job.objects.forEach((object,n)=>object.name='Ring '+(n+1))});
  if(s.data.drafts[0]){s.data.drafts[0].name=s.data.jobs[1].name;s.data.drafts[0].objects=structuredClone(s.data.jobs[1].objects)}
  s.swap_settings.name='A1_swap_example.gcode.3mf';
 }
 // Only the fixture bridge below exists. No native bridge, account, files or printer.
 const boot=`<script>
 const scene=${JSON.stringify(scene)},state=${JSON.stringify(s).replace(/</g,'\\u003c')};
 function canvasImage(kind){
  const c=document.createElement('canvas');c.width=c.height=256;const x=c.getContext('2d');
  if(kind==='top'){
   for(const [a,b] of [[78,78],[164,86],[94,159],[174,171]]){x.fillStyle='#34454a';x.beginPath();x.arc(a,b,17,0,Math.PI*2);x.fill();x.globalCompositeOperation='destination-out';x.beginPath();x.arc(a,b,7,0,Math.PI*2);x.fill();x.globalCompositeOperation='source-over'}
  }else{
   x.fillStyle='#f4f8f7';x.fillRect(0,0,256,256);x.fillStyle='#dce7e4';x.beginPath();x.moveTo(26,145);x.lineTo(136,79);x.lineTo(235,133);x.lineTo(126,206);x.closePath();x.fill();
   for(const [a,b] of [[91,130],[140,112],[129,161],[178,143]]){x.fillStyle='#657c7c';x.beginPath();x.ellipse(a,b+8,21,13,0,0,Math.PI*2);x.fill();x.fillStyle=kind==='blue'?'#49a9b9':'#809999';x.beginPath();x.ellipse(a,b,21,13,0,0,Math.PI*2);x.fill();x.fillStyle='#dce7e4';x.beginPath();x.ellipse(a,b,8,5,0,0,Math.PI*2);x.fill()}
  }
  return c.toDataURL('image/png');
 }
 for(const [i,j] of state.data.jobs.entries())state.data.previews[j.sha256]=canvasImage(i===1?'blue':'model');
 const preview={available:true,width:256,height:256,top:canvasImage('top'),note:state.language==='en'?'Select objects in the top view or the list below. Demo data.':'点击俯视图中的零件，或使用下方列表勾选。演示数据。',regions:state.data.jobs[0].objects.map((o,i)=>{const [x,y]=[[78,78],[164,86],[94,159],[174,171]][i];return {id:o.id,path:'M'+(x-18)+' '+(y-18)+'h36v36h-36z',box:[x-18,y-18,x+18,y+18],center:[x,y]}})};
 window.orca={onMessage(fn){this.listener=fn},postMessage(req){
  if(['refresh','connection_status'].includes(req.action))this.listener({...state,request_id:req.request_id,action:req.action});
  else if(req.action==='object_preview')this.listener({success:true,action:req.action,request_id:req.request_id,queue_id:state.queue_id,job_id:req.id,preview});
  else this.listener({success:false,request_id:req.request_id,note:'离线文档演示，不发送设备操作。'});
 }};
 </script>`;
 const after=`<script>
 setTimeout(async()=>{
  if(scene==='materials')openSettings('draft-example');
  if(scene==='objects'){await openObjects();toggleObject('1419')}
  if(scene==='swap')openSwap();
  if(scene==='connection')document.getElementById('openConnection').click();
  setTimeout(()=>{document.activeElement?.blur();document.body.dataset.docReport=JSON.stringify({scene,width:innerWidth,scroll:document.documentElement.scrollWidth,dialog:document.querySelector('dialog[open]')?.id||null,synthetic:true,controlsOverflow:[...document.querySelectorAll('dialog[open] button,dialog[open] input,dialog[open] select,dialog[open] textarea')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&(r.left<0||r.right>innerWidth+1)}).map(e=>e.id||e.tagName)})},200);
 },200);
 </script>`;
 let html=fs.readFileSync(path.join(root,'plugin_page.html'),'utf8').replace('<link rel="stylesheet" href="plugin_page.css">',()=>'<style>'+fs.readFileSync(path.join(root,'plugin_page.css'),'utf8')+'</style>');
 for(const file of ['page_messages.js','page_i18n.js'])html=html.replace('<script src="'+file+'"></script>',()=>'<script>'+fs.readFileSync(path.join(root,file),'utf8')+'</script>');
html=html.replace('<script src="plugin_page.js"></script>',()=>boot+'<script>'+fs.readFileSync(path.join(root,'plugin_page.js'),'utf8')+'</script>'+after);
if(html.includes('<script src='))throw Error('Page assets were not fully inlined');
 fs.writeFileSync(path.join(out,scene+(language==='en'?'-en':'')+'.html'),html);
}
console.log('Prepared ten bilingual documentation scenes using synthetic data.');
