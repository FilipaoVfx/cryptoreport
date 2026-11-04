// Pruebas de los selectores de tesis con datos sintéticos (no reales).
const test = require('node:test');
const assert = require('node:assert/strict');
const T = require('./theses.js');

const NOW = Date.parse('2026-10-15T12:00:00Z');
const day = (d) => `2026-10-${String(d).padStart(2, '0')}T10:00:00Z`;
function fixture() {
  const videos = [];
  // Diez vídeos del mismo creador sobre ETH: una sola voz.
  for (let i = 0; i < 10; i++) videos.push({ id: `n${i}`, ch: 'nacho', pub: day(5 + (i % 9)), analysis_sha256: `h${i}` });
  videos.push({ id: 'k1', ch: 'kmanu', pub: day(13), analysis_sha256: 'hk' }, { id: 'p1', ch: 'planbtc', pub: day(14), analysis_sha256: 'hp' },
    { id: 's1', ch: 'healthy', pub: day(11), analysis_sha256: 'hs' });
  const radar = (role = 'creador') => ({ speaker_role: role, transcript_hash: 't' });
  const claims = [
    ...videos.filter((v) => v.ch === 'nacho').map((v) => ({ v: v.id, id: 'A1', assets: ['eth'], quote: 'q', radar: radar() })),
    { v: 'k1', id: 'A1', assets: ['eth'], quote: 'q', radar: radar() },
    { v: 'k1', id: 'A2', assets: ['sol'], quote: 'q', radar: radar('tercero_o_no_identificado') }, // cita de terceros: no cuenta
    { v: 'p1', id: 'A1', assets: ['sol'], quote: 'q', radar: radar() },
    { v: 's1', id: 'A1', assets: ['sol'], quote: null, radar: radar() }, // sin cita literal: no cuenta
  ];
  const topics = [{ id: 'eth', section: 'altcoins', videos: [] }, { id: 'sol', section: 'altcoins', videos: [{ v: 's1', n: 3 }] },
    { id: 'ada', section: 'altcoins', videos: [{ v: 's1', n: 2 }] }];
  const theses = { status: 'ok', items: [{ id: 'eth-acum', label: 'ETH acumulación', assets: ['eth'] }, { id: 'alts', label: 'Altcoins esperan', assets: [] }],
    members: [
      ...videos.filter((v) => v.ch === 'nacho').map((v) => ({ t: 'eth-acum', v: v.id, c: 'A1', ch: 'nacho', rel: 'apoyo', dim: 'direccion' })),
      { t: 'eth-acum', v: 'k1', c: 'A1', ch: 'kmanu', rel: 'objecion', dim: 'momento' },
      { t: 'eth-acum', v: 'n9', c: 'A1', ch: 'nacho', rel: 'matiz', dim: 'momento' },
      { t: 'alts', v: 'p1', c: 'A1', ch: 'planbtc', rel: 'apoyo', dim: 'condicion' },
    ] };
  return { videos, claims, topics, theses };
}

test('diez vídeos de un creador cuentan como un creador en ranking y tesis', () => {
  const idx = fixture();
  const eth = T.rankAssets(idx, 'altcoins', {}, NOW).find((r) => r.t.id === 'eth');
  assert.equal(eth.creators, 2); // nacho (10 vídeos) + kmanu
  const st = T.thesisStats(idx, 'eth-acum', {}, NOW);
  assert.equal(st.creators.size, 2);
  assert.equal(st.members.length, 12);
});

test('el total de creadores es una unión, no la suma de columnas; se marca quien está en varios lados', () => {
  const st = T.thesisStats(fixture(), 'eth-acum', {}, NOW);
  const sum = Object.values(st.creatorsBy).reduce((n, s) => n + s.size, 0);
  assert.equal(sum, 3); // nacho en apoyo y matiz + kmanu en objeción
  assert.equal(st.creators.size, 2);
  assert.deepEqual(st.multiSide.map((x) => x.ch), ['nacho']);
});

test('orden: creadores, luego tesis, luego fecha y luego id; las citas de terceros y sin cita no cuentan', () => {
  const rows = T.rankAssets(fixture(), 'altcoins', {}, NOW);
  assert.deepEqual(rows.map((r) => r.t.id), ['eth', 'sol', 'ada']);
  const sol = rows.find((r) => r.t.id === 'sol');
  assert.equal(sol.creators, 1); // solo planbtc: kmanu cita a terceros, healthy no tiene cita
  assert.deepEqual(sol.theses, ['alts']); // vinculada por la afirmación miembro que nombra SOL
  const ada = rows.find((r) => r.t.id === 'ada');
  assert.equal(ada.creators, 0);
  assert.equal(ada.mentionVideos, 1); // menciones de transcripción como métrica aparte
});

test('los filtros de creador y periodo se aplican igual a ranking y tesis', () => {
  const idx = fixture();
  const f = { c: 'kmanu', p: 'todo' };
  const eth = T.rankAssets(idx, 'altcoins', f, NOW).find((r) => r.t.id === 'eth');
  const st = T.thesisStats(idx, 'eth-acum', f, NOW);
  assert.equal(eth.creators, 1);
  assert.equal(st.creators.size, 1);
  assert.deepEqual([...st.creators], ['kmanu']);
  const recent = T.thesisStats(idx, 'eth-acum', { c: 'todos', p: '1d' }, NOW);
  assert.ok(recent.members.every((m) => NOW - Date.parse(idx.videos.find((v) => v.id === m.v).pub) <= 864e5));
});

test('sin proyección de tesis la cobertura es desconocida, no cero tesis', () => {
  const idx = fixture();
  idx.theses = { status: 'error', items: [], members: [] };
  const eth = T.rankAssets(idx, 'altcoins', {}, NOW).find((r) => r.t.id === 'eth');
  assert.equal(eth.coverageKnown, false);
  assert.deepEqual(T.forVideo(idx, 'n1'), []);
});

test('conexiones con X: solo aceptadas, vigentes, del mismo análisis y con el post intacto', () => {
  const idx = fixture();
  const posts = new Map([['p', { content_hash: 'ok' }]]);
  const base = { status: 'aceptado', video_id: 'k1', claim_id: 'A1', analysis_sha256: 'hk', post_id: 'p', post_content_hash: 'ok', expires_at: '2026-10-20T00:00:00Z', relation: 'contrapunto' };
  const run = (c) => T.xConnections(idx, { connections: [c] }, posts, 'eth-acum', {}, NOW);
  assert.equal(run(base).length, 1);
  assert.equal(run({ ...base, expires_at: '2026-10-14T00:00:00Z' }).length, 0); // vencida
  assert.equal(run({ ...base, analysis_sha256: 'otro' }).length, 0); // análisis reemplazado
  assert.equal(run({ ...base, post_content_hash: 'editado' }).length, 0); // post cambiado
  assert.equal(run({ ...base, claim_id: 'A2' }).length, 0); // afirmación fuera de la tesis
  assert.equal(T.X_COUNTS.contexto, false);
  assert.equal(T.X_REL.contexto, 'Contexto; no suma respaldo');
});

test('un ticker coincidente en X es contexto por activo, no apoyo', () => {
  const posts = [{ id: '1', quality: { assets: ['ETH'] } }, { id: '2', quality: { assets: ['SOL'] } }];
  assert.deepEqual(T.assetContext(posts, 'ETH').map((p) => p.id), ['1']);
  assert.deepEqual(T.assetContext(posts, null), []);
});

test('un «cambio» entre autores distintos es contraste entre fuentes, no cambio de postura', () => {
  assert.equal(T.contrastLabel({ kind: 'cambio', sameCreator: false }), 'Contraste entre fuentes');
  assert.equal(T.contrastLabel({ kind: 'cambio', sameCreator: true }), 'Cambio de postura del mismo creador');
});

test('Síntesis: tesis de un vídeo con su relación', () => {
  const r = T.forVideo(fixture(), 'n9');
  assert.equal(r.length, 1);
  assert.equal(r[0].relationLabel, 'Apoya y Matiza');
  assert.deepEqual(r[0].assets, ['eth']);
});

test('una tesis con activos propios no se vincula a otro activo citado de paso; una tesis de grupo sí', () => {
  const idx = fixture();
  idx.claims.push({ v: 'p1', id: 'A9', assets: ['eth', 'ada'], quote: 'q', radar: { speaker_role: 'creador', transcript_hash: 't' } });
  idx.theses.members.push({ t: 'eth-acum', v: 'p1', c: 'A9', ch: 'planbtc', rel: 'apoyo', dim: 'direccion' });
  assert.deepEqual([...T.linkedAssets(idx, idx.theses.items[0])], ['eth']);
  assert.deepEqual([...T.linkedAssets(idx, idx.theses.items[1])], ['sol']);
});
