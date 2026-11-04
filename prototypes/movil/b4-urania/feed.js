/* Pure filters and safe links for attributed posts, without inference. */
(function(root){
  'use strict';
  const normalize=(value)=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  function safeURL(value,avatar=false){
    try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&(!url.port||url.port==='443')&&(!avatar||url.hostname==='pbs.twimg.com')?url.href:null;}catch(_){return null;}
  }
  function select(data,filters,now=Date.now()){
    const accounts=new Map(data.accounts.map(a=>[a.handle,a]));
    return data.posts.filter(p=>{
      const a=accounts.get(p.author_handle),published=Date.parse(p.published_at);
      if(typeof p.id!=='string'||!/^\d+$/.test(p.id)||typeof p.text!=='string')return false;
      if(!a||p.author_id!==a.author_id||!Number.isFinite(published)||published>=now||Date.parse(p.expires_at)<=now||!Number.isFinite(Date.parse(p.expires_at)))return false;
      if(now-published>a.lookback_days*86400000)return false;
      if(filters.account!=='todos'&&filters.account!==p.author_handle)return false;
      if(filters.period==='48h'&&now-published>48*3600000)return false;
      if(filters.quality==='relevante'&&p.quality?.visibility!=='relevante')return false;
      if(filters.quality==='secundario'&&p.quality?.visibility!=='secundario')return false;
      if(filters.length&&filters.length!=='todos'&&p.quality?.length!==filters.length)return false;
      if(filters.narrative&&filters.narrative!=='todas'&&!p.quality?.narratives?.includes(filters.narrative))return false;
      return !filters.q||normalize(p.text+' '+p.author_handle+' '+a.name+' '+(p.quality?.assets||[]).join(' ')+' '+(p.quality?.narratives||[]).join(' ')).includes(normalize(filters.q));
    }).sort((a,b)=>b.published_at.localeCompare(a.published_at)||b.id.localeCompare(a.id));
  }
  function textHTML(value,escape){
    return String(value||'').split(/(https?:\/\/[^\s<>]+)/g).map(part=>{
      if(!/^https?:\/\//.test(part))return escape(part);
      const url=safeURL(part);
      return url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(part)}</a>`:escape(part);
    }).join('');
  }
  const api={select,safeURL,textHTML};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.UraniaFeed=api;
})(typeof window!=='undefined'?window:globalThis);
