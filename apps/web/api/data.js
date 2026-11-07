// Vercel injects DATA_SERVICE_URL into this function at runtime.
// No origin or origin credentials are consumed by this public gateway.
module.exports = require('../../../services/data/lib/reader.js')({
  originEnv: 'DATA_SERVICE_URL', authEnv: null, internal: true,
});
