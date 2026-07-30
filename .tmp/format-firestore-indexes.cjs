const fs = require('fs');
const path = 'firestore.indexes.json';
const data = JSON.parse(fs.readFileSync(path, 'utf8'));
const formatField = (field) => `{ ${Object.entries(field).map(([key, value]) => `${JSON.stringify(key)}: ${JSON.stringify(value)}`).join(', ')} }`;
const lines = ['{', '  "indexes": ['];
data.indexes.forEach((index, indexPosition) => {
  lines.push(
    '    {',
    `      "collectionGroup": ${JSON.stringify(index.collectionGroup)},`,
    `      "queryScope": ${JSON.stringify(index.queryScope)},`,
    '      "fields": ['
  );
  index.fields.forEach((field, fieldPosition) => {
    const suffix = fieldPosition === index.fields.length - 1 ? '' : ',';
    lines.push(`        ${formatField(field)}${suffix}`);
  });
  const suffix = indexPosition === data.indexes.length - 1 ? '' : ',';
  lines.push('      ]', `    }${suffix}`);
});
lines.push('  ],', '  "fieldOverrides": []', '}', '');
fs.writeFileSync(path, lines.join('\n'));
