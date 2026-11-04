/* Briefs de presentación revisados contra el análisis guardado. No alteran sus fuentes.
   Se ocultan si cambia el hash: un resumen antiguo nunca representa un análisis nuevo. */
(function (root) {
  'use strict';
  const briefs = {
    pcBbfvFmkY0: ['c5529f4b34613a93c5e2017a6e49bb862a47c83ce942400ab14b462f92e0f41f',
      'Battaglia plantea un cierre de Bitcoin sobre $100,000 a final de año.',
      'Lo condiciona a que no haya nuevas subidas de tipos, BTC conserve «80» y progrese el Golden Cross. La unidad de «80» no queda aclarada.'],
    d53ZVorywvk: ['6195110f200230b2c79ec997d6c891f866a1fba9a965b1e4bd2f70f805d5f50d',
      'Nacho vincula la escasez de liquidez con un dólar más fuerte y deuda más cara.',
      'Lo presenta como un ciclo de unos cuatro años; la repetición requiere contrastar series y periodos.'],
    '40Jh8ABy83o': ['d618fe068067923edf574a8033fcb0af29cc209d8fde702dbb3a9f6edcafe3f5',
      'Healthy Pockets defiende acumular Bitcoin a largo plazo ante la erosión del dinero fiat.',
      'Su tesis depende de la escasez y la demanda de BTC. No fija un horizonte ni un umbral para comprobar esa protección.'],
    LcJTmXpKM7E: ['58837dfbd27d2d3addcc7677957ef5672165194c305784de1e5edfc9a7ab659e',
      'Plan BTC anticipa una corrección en Bitcoin y Nasdaq, con posibilidad de un rebote previo.',
      'Combina patrones técnicos y comparaciones electorales. Sus distintos porcentajes y ventanas no forman una única predicción.'],
    ssdHOY7wVMk: ['57cfda4a6e0d3d7e9b3bd7f93ba60fc6057339864dbdfa0eb058503ed8ff8f46',
      'Nacho interpreta el miedo como una posible oportunidad de acumulación dentro de un ciclo alcista.',
      'Perder el soporte citado podría prolongar la caída; su sesgo alcista desde el 28 de octubre sigue siendo una predicción.'],
    aW9a3O2XNho: ['000baa0f42f570d94e1ebeb2d011720a462a89a7528f2a7eb136a1a093caaf5a',
      'Cava distingue una Suiza sólida a largo plazo de una bolsa vulnerable a corto plazo.',
      'Mantiene la lectura bajista del índice suizo bajo 14.100. Buscaría compra bajo 12500 solo si identifica agotamiento.'],
    zQ6nDHqcG7Q: ['ab08f995f1a204658c8885352eb1f74d56303e5621230d9ee3d894e0ebcac644',
      'Nacho contrapone los máximos del S&P 500 a la presión de la oferta de deuda.',
      'La cifra de refinanciación y su efecto sobre los bonos requieren una fuente original; la divergencia no demuestra causalidad.'],
  };
  function brief(id, hash) {
    const b = briefs[id];
    return b && b[0] === hash ? { thesis: b[1], condition: b[2] } : null;
  }
  function listTitle(title) {
    // Solo presentación: el título original permanece en la fuente y el detalle.
    return String(title || '').replace(/(^|\s)#[\p{L}\p{N}_]+/gu, ' ').replace(/\s+/g, ' ').trim() || title;
  }
  const api = { brief, listTitle };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.UraniaEditorial = api;
})(typeof window !== 'undefined' ? window : globalThis);
