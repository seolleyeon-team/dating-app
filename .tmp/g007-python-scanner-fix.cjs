const fs = require('fs');
function replaceRequired(path, oldText, newText, label) {
  const content = fs.readFileSync(path, 'utf8');
  const first = content.indexOf(oldText);
  const second = content.indexOf(oldText, first + 1);
  if (first < 0 || second >= 0) throw new Error(`${label}: expected exactly one match`);
  fs.writeFileSync(path, content.replace(oldText, newText));
}
replaceRequired(
  'scripts/privacy_client_scanner.py',
  '    r"\\b(uid|email|token|url|uri|path|sourcephotourl|error|stack|stacktrace|request|response|userinfo|nickname|user)\\b",',
  '    r"\\b[A-Za-z_]\\w*(uid|userId|kakaoUserId|firebaseUid|authorId|writerId|email|token|url|uri|path|sourcephotourl|error|stack|stacktrace|request|response|userinfo|nickname|user)\\w*\\b",',
  'python identity alias scanner'
);
replaceRequired(
  'tests/test_qa_media_privacy_phase3f.py',
  `  required String sourcePhotoUrl,\n  required Object e,`,
  `  required String sourcePhotoUrl,\n  required String authorIdStr,\n  required String currentUserId,\n  required Object e,`,
  'python scanner alias fixture parameters'
);
replaceRequired(
  'tests/test_qa_media_privacy_phase3f.py',
  `  debugPrint('uid=\$uid email=\$email token=\$token source=\$sourcePhotoUrl error=\$e stack=\$st');`,
  `  debugPrint('uid=\$uid email=\$email token=\$token source=\$sourcePhotoUrl error=\$e stack=\$st');\n  debugPrint('author=\$authorIdStr current=\$currentUserId');`,
  'python scanner alias fixture log'
);
