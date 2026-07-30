const fs = require('fs');

function patch(path, transform) {
  const before = fs.readFileSync(path, 'utf8');
  const after = transform(before);
  if (after === before) throw new Error(`${path}: no change made`);
  fs.writeFileSync(path, after);
}

function replaceExactly(content, pattern, replacement, expected, label) {
  const matches = content.match(pattern) ?? [];
  if (matches.length !== expected) throw new Error(`${label}: expected ${expected}, found ${matches.length}`);
  return content.replace(pattern, replacement);
}

patch('lib/data/repositories/firestore_community_repository.dart', (content) => {
  content = replaceExactly(
    content,
    /^    debugPrint\('\[FirestoreCommunity\] createPost authorId="\$authorIdStr"'\);\r?\n/mg,
    '',
    1,
    'createPost raw author log'
  );
  content = replaceExactly(
    content,
    /^    if \(tab\.trim\(\) == .*?\{\r?\n      debugPrint\([\s\S]*?^      \);\r?\n    \}\r?\n\r?\n/mg,
    '',
    1,
    'current user query log'
  );
  content = replaceExactly(
    content,
    /^      if \(snapshot\.docs\.isNotEmpty\) \{\r?\n        final first = snapshot\.docs\.first\.data\(\);\r?\n        debugPrint\('[\s\S]*?^      \}\r?\n/mg,
    '',
    1,
    'first author log'
  );
  return content;
});

patch('test/privacy_log_redaction_test.dart', (content) => {
  content = replaceExactly(
    content,
    /r'\(\?:\^\|\[\^A-Za-z0-9_\.\$\]\)\(\?:uid\|userId\|kakaoUserId\|firebaseUid\|email\|nickname\|phone\)\(\?:\$\|\[\^A-Za-z0-9_\]\)'/,
    "r'(?:^|[^A-Za-z0-9_.$])[A-Za-z_][A-Za-z0-9_]*(?:uid|userId|kakaoUserId|firebaseUid|authorId|writerId|email|nickname|phone)[A-Za-z0-9_]*(?:$|[^A-Za-z0-9_])'",
    1,
    'raw identity alias regex'
  );
  content = replaceExactly(
    content,
    /\|phone\|token\|url\|uri\|storagePath/,
    '|phone|authorId|writerId|token|url|uri|storagePath',
    1,
    'map identity aliases'
  );
  const insertion = `\n  test('privacy scanner catches identity aliases in interpolated logs', () {\n    const source = r'''\nvoid example(String authorIdStr, String currentUserId, Map<String, Object?> row) {\n  debugPrint('author=\$authorIdStr');\n  debugPrint('current=\$currentUserId');\n  debugPrint('first=\${row['authorId']}');\n}\n''';\n\n    expect(_unsafeLogFindings(source), hasLength(3));\n  });\n`;
  content = replaceExactly(
    content,
    /\n  test\('privacy log utility fingerprints do not contain raw input'/,
    `${insertion}\n  test('privacy log utility fingerprints do not contain raw input'`,
    1,
    'scanner alias regression test'
  );
  return content;
});

patch('lib/services/team_meeting_request_service.dart', (content) => {
  const helper = `\n  Future<String> _requireFirebaseReadSession() async {\n    final userId = await _storageService.getKakaoUserId();\n    if (userId == null || userId.isEmpty) {\n      throw StateError('로그인이 필요해요.');\n    }\n    final attached = await _authService.ensureFirebaseSessionForKakao(userId);\n    if (!attached) {\n      throw StateError('로그인 세션을 확인하지 못했어요. 다시 로그인해주세요.');\n    }\n    return userId;\n  }\n`;
  content = replaceExactly(
    content,
    /  final StorageService _storageService;\r?\n/,
    `  final StorageService _storageService;\n${helper}`,
    1,
    'read session helper'
  );
  content = replaceExactly(
    content,
    /    final kakaoUserId = await _storageService\.getKakaoUserId\(\);\r?\n    if \(kakaoUserId == null \|\| kakaoUserId\.isEmpty\) \{\r?\n      throw StateError\('[\s\S]*?^    \}\r?\n    await _authService\.ensureFirebaseSessionForKakao\(kakaoUserId\);/mg,
    '    final kakaoUserId = await _requireFirebaseReadSession();',
    1,
    'callable session requirement'
  );
  content = replaceExactly(
    content,
    /    final userId = await _storageService\.getKakaoUserId\(\);\r?\n    if \(userId == null \|\| userId\.isEmpty\) \{\r?\n      yield const <TeamMeetingRequestDoc>\[\];\r?\n      return;\r?\n    \}/,
    '    final userId = await _requireFirebaseReadSession();',
    1,
    'team request stream session'
  );
  content = replaceExactly(
    content,
    /  Stream<TeamMeetingRequestDoc\?> watchRequest\(String requestId\) \{\r?\n    return _firestore/,
    '  Stream<TeamMeetingRequestDoc?> watchRequest(String requestId) async* {\n    await _requireFirebaseReadSession();\n    yield* _firestore',
    1,
    'request stream session'
  );
  content = replaceExactly(
    content,
    /  Future<TeamMeetingMatchDoc\?> getMatchOnce\(String matchId\) async \{\r?\n    final snapshot/,
    '  Future<TeamMeetingMatchDoc?> getMatchOnce(String matchId) async {\n    await _requireFirebaseReadSession();\n    final snapshot',
    1,
    'match get session'
  );
  content = replaceExactly(
    content,
    /  Stream<TeamMeetingMatchDoc\?> watchMatch\(String matchId\) \{\r?\n    return _firestore/,
    '  Stream<TeamMeetingMatchDoc?> watchMatch(String matchId) async* {\n    await _requireFirebaseReadSession();\n    yield* _firestore',
    1,
    'match stream session'
  );
  content = replaceExactly(
    content,
    /  Future<TeamMeetingRequestDoc\?> getRequestOnce\(String requestId\) async \{\r?\n    final snapshot/,
    '  Future<TeamMeetingRequestDoc?> getRequestOnce(String requestId) async {\n    await _requireFirebaseReadSession();\n    final snapshot',
    1,
    'request get session'
  );
  return content;
});
