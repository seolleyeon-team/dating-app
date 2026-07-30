const fs = require('fs');

function patch(path, transform) {
  const before = fs.readFileSync(path, 'utf8');
  const after = transform(before);
  if (after === before) throw new Error(`${path}: no change made`);
  fs.writeFileSync(path, after);
}

function replaceExactly(content, pattern, replacement, count, label) {
  const matches = content.match(pattern) ?? [];
  if (matches.length !== count) {
    throw new Error(`${label}: expected ${count} matches, found ${matches.length}`);
  }
  return content.replace(pattern, replacement);
}

patch('functions/src/chatRealPhoto.ts', (content) => {
  content = replaceExactly(
    content,
    /import \{ chatProfilePhotoBucket \} from "\.\/avatarMedia";\r?\n/,
    'import { chatProfilePhotoBucket } from "./avatarMedia";\nimport { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";\n',
    1,
    'chat policy import'
  );
  content = replaceExactly(
    content,
    /function safeDecodeUriComponent\(value: string\): string \{[\s\S]*?\n\}\n\nfunction isSafeRuntimePublicAvatarUrl\(value: unknown\): boolean \{[\s\S]*?\n\}\n\nexport function resolveSafeApprovedAvatarUrl/,
    'export function resolveSafeApprovedAvatarUrl',
    1,
    'chat local URL policy'
  );
  content = replaceExactly(
    content,
    /isSafeRuntimePublicAvatarUrl/g,
    'isSafePublicAvatarUrl',
    2,
    'chat URL policy calls'
  );
  return content;
});

patch('functions/src/avatarApproval.ts', (content) => {
  content = replaceExactly(
    content,
    /import sharp from "sharp";\r?\n/,
    'import sharp from "sharp";\nimport { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";\n',
    1,
    'approval policy import'
  );
  content = replaceExactly(
    content,
    /function safeDecodeUriComponent\(value: string\): string \{[\s\S]*?\n\}\n\nfunction isSafePublicApprovedAvatarUrl\(value: unknown\): value is string \{[\s\S]*?\n\}\n\nfunction requirePathSegment/,
    'function requirePathSegment',
    1,
    'approval local URL policy'
  );
  content = replaceExactly(
    content,
    /isSafePublicApprovedAvatarUrl/g,
    'isSafePublicAvatarUrl',
    1,
    'approval URL policy call'
  );
  return content;
});
