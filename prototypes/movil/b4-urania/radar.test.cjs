const {test} = require('node:test');
const assert = require('node:assert/strict');
const R = require('./radar.js');
const topics = [{id:'eth',name:'Ethereum',sym:'ETH',section:'altcoins',claims:[]},{id:'btc',name:'Bitcoin',sym:'BTC',section:'bitcoin',claims:[]}];
const now = Date.parse('2026-10-14T12:00:00Z');
function fixture() {
  const videosById = {a:{id:'a',ch:'one',pub:'2026-10-14T10:00:00Z'},b:{id:'b',ch:'one',pub:'2026-10-14T09:00:00Z'},c:{id:'c',ch:'two',pub:'2026-10-01T09:00:00Z'}};
  const claims = ['a','b','c'].map((v,i)=>({v,id:`A${i}`,assets:['eth'],quote:`Quote ${i}`,text:`Claim ${i}`,t:i,pol:'neutra',radar:{eligible:true,direction:'bajista',position_side:null,position_status:'desconocida'}}));
  return {videosById,claims,topics:structuredClone(topics),claimsByKey:Object.fromEntries(claims.map(c=>[`${c.v}:${c.id}`,c]))};
}
test('short ETH resolves canonical asset',()=>assert.deepEqual(R.parse('short ETH',topics),{direction:'bajista',term:'eth',asset:'eth',unresolved:false,candidates:[topics[0]]}));
test('ordinary search, negations, Shorts and closed positions are not hijacked',()=>{
  for(const q of ['shorts','largo plazo','no quiero short','cerró su short','Google','longitud']) assert.equal(R.parse(q,topics),null,q);
});
test('unknown or colliding tickers never broaden to all assets',()=>{
  assert.equal(R.parse('short XYZ',topics).unresolved,true);
  assert.equal(R.parse('long ETH',[...topics,{id:'other',sym:'ETH'}]).unresolved,true);
  assert.equal(R.rows(fixture(),R.parse('short XYZ',topics),{}).length,0);
});
test('rolling periods are measured from current time and exclude future dates',()=>{
  assert.equal(R.inWindow({ch:'one',pub:'2026-10-12T13:00:00Z'},{p:'2d'},now),true);
  assert.equal(R.inWindow({ch:'one',pub:'2026-10-12T11:00:00Z'},{p:'2d'},now),false);
  assert.equal(R.inWindow({ch:'one',pub:'2026-10-15T11:00:00Z'},{p:'2d'},now),false);
});
test('repeat videos by one author do not inflate creator count',()=>{
  const row=R.rows(fixture(),R.parse('short',topics),{c:'one',p:'todo'},now)[0];
  assert.equal(row.creators,1); assert.equal(row.videos,2);
});
test('creator and period filters produce consistent evidence',()=>{
  const idx=fixture(), t={...topics[0],claims:idx.claims.map(c=>({v:c.v,id:c.id}))};
  const filters={p:'2d',c:'one'};
  assert.equal(R.rows(idx,R.parse('short',topics),filters,now)[0].claims.length,2);
  // Evidence uses the real clock; use all-time for this half of the creator check.
  assert.equal(R.evidence(idx,t,[],{p:'todo',c:'two'}).length,1);
});
test('bearish tone alone does not pass declared-short filter',()=>{
  const idx=fixture(); assert.equal(R.rows(idx,R.parse('short',topics),{own:'1'},now).length,0);
  Object.assign(idx.claims[0].radar,{position_side:'short',position_status:'declarada'});
  assert.equal(R.rows(idx,R.parse('short',topics),{own:'1'},now)[0].claims.length,1);
});
test('closed or third-party evidence does not establish a declared position',()=>{
  const idx=fixture(); Object.assign(idx.claims[0].radar,{position_side:'short',position_status:'cerrada'}); idx.claims[1].radar.eligible=false;
  assert.equal(R.rows(idx,R.parse('short',topics),{own:'1'},now).length,0);
});
test('asset-specific exception overrides the generic thesis',()=>{
  const idx=fixture(); idx.claims.forEach(c=>c.radar.asset_directions={eth:'neutra'});
  assert.equal(R.rows(idx,R.parse('short ETH',topics),{},now).length,0);
});
test('global grouping puts neutral analyses after directional transcript quotes',()=>{
  const idx=fixture(); idx.claims[0].radar.direction='neutra';
  const t={...topics[0],claims:[{v:'a',id:'A0'}]};
  const items=R.evidence(idx,t,[{v:'b',t:10,text:'Bullish quote',pol:'alcista'},{v:'b',t:20,text:'Bearish quote',pol:'bajista'}],{});
  assert.deepEqual(items.map(x=>x.pol),['alcista','bajista','neutra']);
});
test('same passage is not repeated as a detected and analyzed quote',()=>{
  const idx=fixture(),t={...topics[0],claims:[{v:'a',id:'A0'}]};
  assert.equal(R.evidence(idx,t,[{v:'a',t:0,text:'Quote 0',pol:'neutra'}],{}).length,1);
});
test('opposing horizons in the same passage survive deduplication',()=>{
  const idx=fixture();idx.claims[1].v='a';idx.claims[1].quote='Quote 0';idx.claims[1].radar.direction='alcista';
  idx.claims[0].radar.horizon='Corto plazo';idx.claims[1].radar.horizon='Largo plazo';
  idx.claimsByKey['a:A1']=idx.claims[1];
  const t={...topics[0],claims:[{v:'a',id:'A0'},{v:'a',id:'A1'}]};
  const result=R.evidence(idx,t,[],{});
  assert.equal(result.length,1);assert.equal(result[0].pol,'mixta');
  assert.match(result[0].radar.horizon,/Corto plazo/);assert.match(result[0].radar.horizon,/Largo plazo/);
});
