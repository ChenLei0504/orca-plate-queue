/* Page-only localization. No networking, credentials or machine actions. */
(function(global){
  'use strict';
  const english=global.QueueMessages.en,rawPatterns=global.QueueMessages.patterns;
  const has=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
  const languages=new Set(['zh-CN','en']);
  let language='zh-CN';
  const originals=new Map(),textBindings=[],attributeBindings=[];
  const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const patterns=rawPatterns.map(([source,target])=>{
    const parts=source.split(/\{[^}]+\}/g),regex=new RegExp('^'+parts.map(escape).join('([\\s\\S]*?)')+'$');
    return {source,target,regex,score:parts.join('').length,
      opaque:/^(?:切片耗材|加入 |发送：|已读取：|已保存|换盘文件有效|文件|模拟开始|运行记录已保存|跨盘续料)/.test(source)};
  }).sort((a,b)=>b.score-a.score);
  function remember(result,source){
    if(result&&result!==source){if(originals.size>=1024)originals.delete(originals.keys().next().value);originals.set(result,source)}
    return result;
  }
  function original(value){return originals.get(value)||value}
  function tr(value,params){
    const source=String(value??'');
    let result=language==='en'?(english[source]??source):source;
    if(params)result=result.replace(/\{([^}]+)\}/g,(all,key)=>has(params,key)?String(params[key]):all);
    const renderedSource=params?source.replace(/\{([^}]+)\}/g,(all,key)=>has(params,key)?String(params[key]):all):source;
    return remember(result,renderedSource);
  }
  function message(value,depth=0){
    let source=original(String(value??''));
    if(language!=='en'||!source)return source;
    if(has(english,source))return remember(english[source],source);
    if(depth>5||source.length>16384)return source;
    const timestamp=source.match(/^(\d\d-\d\d \d\d:\d\d:\d\d\s+)([\s\S]*)$/);
    if(timestamp)return remember(timestamp[1]+message(timestamp[2],depth+1),source);
    if(source.includes('\n'))return remember(source.split('\n').map(line=>message(line,depth+1)).join('\n'),source);
    const code=source.match(/^(.+)（(-?\d+)）$/);
    if(code&&has(english,code[1]))return remember(english[code[1]]+' ('+code[2]+')',source);
    for(const item of patterns){
      const match=item.regex.exec(source);
      if(match){const result=item.target.replace(/\{(\d+)\}/g,(_,index)=>item.opaque?match[Number(index)+1]:message(match[Number(index)+1],depth+1));return remember(result,source)}
    }
    return source;
  }
  function initialize(document){
    const walker=document.createTreeWalker(document.documentElement,global.NodeFilter.SHOW_TEXT);
    let text;
    while((text=walker.nextNode())){
      if(text.parentElement.closest('script,style,[data-i18n-ignore]'))continue;
      if(/[\u3400-\u9fff]/.test(text.nodeValue))textBindings.push({node:text,source:text.nodeValue});
    }
    for(const element of document.querySelectorAll('*')){
      for(const name of ['title','placeholder','aria-label']){
        const source=element.getAttribute(name);
        if(source&&/[\u3400-\u9fff]/.test(source))attributeBindings.push({element,name,source,last:source});
      }
    }
    applyStatic(document);
  }
  function staticText(source){
    if(language==='zh-CN')return source;
    if(has(english,source))return tr(source);
    const text=source.trim(),start=source.indexOf(text);
    return source.slice(0,start)+message(text)+source.slice(start+text.length);
  }
  function applyStatic(document){
    document.documentElement.lang=language;
    for(const {node,source} of textBindings)if(node.isConnected)node.nodeValue=staticText(source);
    for(const item of attributeBindings)if(item.element.isConnected){
      const current=item.element.getAttribute(item.name);
      if(current===item.source||current===item.last){item.last=staticText(item.source);item.element.setAttribute(item.name,item.last)}
    }
    document.title=tr('打印队列');
  }
  function setLanguage(value,document){
    if(!languages.has(value))return false;
    language=value;
    if(document)applyStatic(document);
    return true;
  }
  function duration(value){
    if(value===null||value===undefined||!Number.isFinite(Number(value)))return tr('耗时未知');
    const minutes=Math.round(Number(value)/60);
    return (minutes>=60?Math.floor(minutes/60)+tr(' 小时 '):'')+minutes%60+tr(' 分钟');
  }
  global.QueueI18n=Object.freeze({tr,message,original,initialize,applyStatic,setLanguage,duration,
    supports:value=>languages.has(value),get language(){return language},
    number:value=>new Intl.NumberFormat(language==='en'?'en-US':'zh-CN',{maximumFractionDigits:1}).format(value)});
})(window);
