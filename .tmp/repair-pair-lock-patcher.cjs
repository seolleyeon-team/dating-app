const fs = require('fs');
const path = '.tmp/g007-team-pair-lock.cjs';
const before = fs.readFileSync(path, 'utf8');
const pattern = /          throw new HttpsError\("not-found", ".*?"\);/;
if ((before.match(new RegExp(pattern.source, 'g')) ?? []).length !== 1) {
  throw new Error('expected one hardcoded result error in pair-lock patcher');
}
const replacement = '          throw new HttpsError("not-found", "\\uB9E4\\uCE6D \\uACB0\\uACFC\\uB97C \\uCC3E\\uC744 \\uC218 \\uC5C6\\uC5B4\\uC694.");';
fs.writeFileSync(path, before.replace(pattern, replacement));
