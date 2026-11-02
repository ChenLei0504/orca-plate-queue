/* Synthetic offline connection setup view; no native libraries or personal data. */
const fs=require('node:fs'),path=require('node:path');
const {bundledFixture}=require('./test_page.cjs');
const state=bundledFixture();state.data.jobs=[];state.data.previews={};state.setup={};state.swap_plan=[];
state.build_id='20261102.3';state.connection.devices[0].monitor_epoch='offline-example-history';
state.components.series.push({series:'02.08.01',kind:'missing',compatible:false,loaded:false});
state.components.series.sort((a,b)=>a.series.localeCompare(b.series));
const out=path.join(__dirname,'verification/public-release');fs.mkdirSync(out,{recursive:true});
const bridge=`<script>const fixture=${JSON.stringify(state).replace(/</g,'\\u003c')};window.orca={onMessage(fn){this.listener=fn},postMessage(req){if(['refresh','connection_status'].includes(req.action))this.listener({...fixture,request_id:req.request_id,action:req.action});else this.listener({success:false,request_id:req.request_id,note:'离线展示，不执行安装或打印。'})}};</script>`;
const after=`<script>document.getElementById('openConnection').click();setTimeout(()=>{document.body.dataset.report=JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,dialog:document.getElementById('connectionDialog').getBoundingClientRect().toJSON(),overflow:[...document.querySelectorAll('dialog[open] *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>e.id||e.className)})},100);</script>`;
let html=fs.readFileSync('plugin_page.html','utf8').replace('<link rel="stylesheet" href="plugin_page.css">',()=>'<style>'+fs.readFileSync('plugin_page.css','utf8')+'</style>');
for(const file of ['page_messages.js','page_i18n.js'])html=html.replace('<script src="'+file+'"></script>',()=>'<script>'+fs.readFileSync(path.join(__dirname,file),'utf8')+'</script>');
html=html.replace('<script src="plugin_page.js"></script>',()=>bridge+'<script>'+fs.readFileSync('plugin_page.js','utf8')+'</script>'+after);
if(html.includes('<script src='))throw Error('Page assets were not fully inlined');
fs.writeFileSync(path.join(out,'preview.html'),html);console.log(path.join(out,'preview.html'));
