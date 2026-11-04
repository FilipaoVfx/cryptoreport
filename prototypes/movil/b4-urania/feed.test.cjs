const {test}=require('node:test');
const assert=require('node:assert/strict');
const F=require('./feed.js');
const now=Date.parse('2026-10-15T12:00:00Z');
const data={accounts:[{handle:'one',author_id:'10',name:'Cuenta Uno',lookback_days:4},{handle:'two',author_id:'20',name:'Dos',lookback_days:15}],posts:[
  {id:'1',author_handle:'one',author_id:'10',published_at:'2026-10-14T12:00:00Z',expires_at:'2026-10-18T12:00:00Z',text:'Ethereum y dólar'},
  {id:'2',author_handle:'two',author_id:'20',published_at:'2026-10-10T12:00:00Z',expires_at:'2026-10-25T12:00:00Z',text:'Desarrollo de Ethereum'},
]};
const filters={account:'todos',period:'cuenta',q:''};
test('account windows differ and 48h filters correctly',()=>{
  assert.equal(F.select(data,filters,now).length,2);
  assert.equal(F.select(data,{...filters,period:'48h'},now).length,1);
  assert.equal(F.select(data,{...filters,account:'two'},now)[0].id,'2');
});
test('search normalizes accents without generating analysis',()=>{
  assert.equal(F.select(data,{...filters,q:'dolar'},now).length,1);
  assert.equal(F.select(data,{...filters,q:'nonexistent'},now).length,0);
});
test('expired and future posts disappear even in cached feed',()=>{
  assert.equal(F.select(data,filters,Date.parse('2026-10-26T12:00:00Z')).length,0);
  assert.equal(F.select(data,filters,Date.parse('2026-10-01T12:00:00Z')).length,0);
});
test('unknown account and mismatched pinned author do not render',()=>{
  const changed=structuredClone(data);changed.posts[0].author_id='99';changed.posts[1].author_handle='other';
  assert.equal(F.select(changed,filters,now).length,0);
});
test('invalid identifiers and absent expiration are rejected',()=>{
  const changed=structuredClone(data);changed.posts[0].id='" onload="alert(1)';delete changed.posts[1].expires_at;
  assert.equal(F.select(changed,filters,now).length,0);
});
test('URLs require HTTPS and avatar origin is restricted',()=>{
  for(const value of ['javascript:alert(1)','data:text/html,x','https://u:p@x.com','http://x.com'])assert.equal(F.safeURL(value),null);
  assert.equal(F.safeURL('https://evil.test/photo.jpg',true),null);
  assert.equal(F.safeURL('https://pbs.twimg.com/profile_images/photo.jpg',true),'https://pbs.twimg.com/profile_images/photo.jpg');
});
test('post HTML is escaped while safe URLs remain clickable',()=>{
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rendered=F.textHTML('<script>alert(1)</script> https://example.com/news',escape);
  assert.ok(!rendered.includes('<script>'));assert.ok(rendered.includes('&lt;script&gt;'));assert.ok(rendered.includes('rel="noopener noreferrer"'));
});
test('editorial filters separate relevant posts and preserve access to conversations',()=>{
  const classified=structuredClone(data);
  classified.posts[0].quality={visibility:'relevante',length:'breve',assets:['ETH'],narratives:['consenso']};
  classified.posts[1].quality={visibility:'secundario',length:'micro',assets:[],narratives:[]};
  assert.deepEqual(F.select(classified,{...filters,quality:'relevante'},now).map(p=>p.id),['1']);
  assert.deepEqual(F.select(classified,{...filters,quality:'secundario'},now).map(p=>p.id),['2']);
  assert.equal(F.select(classified,{...filters,quality:'todos'},now).length,2);
  assert.equal(F.select(classified,{...filters,narrative:'consenso',length:'breve'},now).length,1);
  assert.equal(F.select(classified,{...filters,narrative:'seguridad'},now).length,0);
  assert.equal(F.select(classified,{...filters,q:'ETH'},now).length,2);
});
