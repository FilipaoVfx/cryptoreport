// Única función pública. Lee solo JSON publicado y validado desde el origen del VPS.
// Modo por defecto del lector: CR_DATA_ORIGIN + CR_DATA_AUTHORIZATION, ambos solo de servidor.
module.exports = require('../lib/reader.js')();
