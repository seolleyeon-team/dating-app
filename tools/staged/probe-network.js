// probe: contains a network call, must be blocked by the content scan
const https = require('https');
https.get('https://example.com/collect', (res) => {
  console.log(res.statusCode);
});
