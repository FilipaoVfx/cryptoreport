const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('./editorial.js');

test('un brief solo se aplica al análisis exacto revisado', () => {
  const hash = 'c5529f4b34613a93c5e2017a6e49bb862a47c83ce942400ab14b462f92e0f41f';
  const b = E.brief('pcBbfvFmkY0', hash);
  assert.match(b.thesis, /plantea/);
  assert.match(b.condition, /no haya nuevas subidas/);
  assert.match(b.condition, /«80»/);
  assert.match(b.condition, /unidad.*no queda aclarada/);
  assert.equal(E.brief('pcBbfvFmkY0', 'otro análisis'), null);
  assert.equal(E.brief('pcBbfvFmkY0', undefined), null);
  assert.equal(E.brief('video nuevo', hash), null);
});

test('el título de lista oculta hashtags sin suprimir las palabras ni sus condiciones', () => {
  assert.equal(E.listTitle('BTC no subirá si pierde soporte #Bitcoin #cripto'), 'BTC no subirá si pierde soporte');
  assert.equal(E.listTitle('Objetivo: $100,000; soporte «80»'), 'Objetivo: $100,000; soporte «80»');
  assert.equal(E.listTitle('#solo_hashtag'), '#solo_hashtag');
});
