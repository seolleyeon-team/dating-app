const fs = require('fs');
const path = 'functions/src/teamMeetingRequest.ts';
const before = fs.readFileSync(path, 'utf8');
const pattern = /(        if \(!resultSnap\.exists \|\| resultSnap\.data\(\) == null\) \{\r?\n)          throw new HttpsError\("not-found", ".*?"\);/;
const matches = before.match(new RegExp(pattern.source, 'g')) ?? [];
if (matches.length !== 1) throw new Error(`expected one result error message, found ${matches.length}`);
const after = before.replace(pattern, '$1          throw new HttpsError("not-found", "매칭 결과를 찾을 수 없어요.");');
fs.writeFileSync(path, after);
