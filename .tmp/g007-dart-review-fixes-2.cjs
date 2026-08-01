const fs = require('fs');

function replaceRequired(path, oldText, newText, label) {
  const content = fs.readFileSync(path, 'utf8');
  const first = content.indexOf(oldText);
  const second = content.indexOf(oldText, first + 1);
  if (first < 0 || second >= 0) throw new Error(`${label}: expected exactly one match`);
  fs.writeFileSync(path, content.replace(oldText, newText));
}

const scannerPath = 'test/privacy_log_redaction_test.dart';
replaceRequired(
  scannerPath,
  "  r'(?:^|[^A-Za-z0-9_])(?:uid|userId|kakaoUserId|firebaseUid|email|nickname|phone)(?:$|[^A-Za-z0-9_])',",
  "  r'(?:^|[^A-Za-z0-9_.$])[A-Za-z_][A-Za-z0-9_]*(?:uid|userId|kakaoUserId|firebaseUid|authorId|writerId|email|nickname|phone)[A-Za-z0-9_]*(?:$|[^A-Za-z0-9_])',",
  'raw identity alias regex'
);
replaceRequired(
  scannerPath,
  '|firebaseUid|email|nickname|phone|token|url|uri|storagePath|',
  '|firebaseUid|email|nickname|phone|authorId|writerId|token|url|uri|storagePath|',
  'map identity aliases'
);
replaceRequired(
  scannerPath,
  "\n  test('privacy log utility fingerprints do not contain raw input'",
  `\n  test('privacy scanner catches identity aliases in interpolated logs', () {\n    const source = r'''\nvoid example(String authorIdStr, String currentUserId, Map<String, Object?> row) {\n  debugPrint('author=\$authorIdStr');\n  debugPrint('current=\$currentUserId');\n  debugPrint('first=\${row['authorId']}');\n}\n''';\n\n    expect(_unsafeLogFindings(source), hasLength(3));\n  });\n\n  test('privacy log utility fingerprints do not contain raw input'`,
  'scanner alias regression test'
);

const servicePath = 'lib/services/team_meeting_request_service.dart';
replaceRequired(
  servicePath,
  '  final StorageService _storageService;\n',
  `  final StorageService _storageService;\n\n  Future<String> _requireFirebaseReadSession() async {\n    final userId = await _storageService.getKakaoUserId();\n    if (userId == null || userId.isEmpty) {\n      throw StateError('로그인이 필요해요.');\n    }\n    final attached = await _authService.ensureFirebaseSessionForKakao(userId);\n    if (!attached) {\n      throw StateError('로그인 세션을 확인하지 못했어요. 다시 로그인해주세요.');\n    }\n    return userId;\n  }\n`,
  'read session helper'
);
replaceRequired(
  servicePath,
  `    final kakaoUserId = await _storageService.getKakaoUserId();\n    if (kakaoUserId == null || kakaoUserId.isEmpty) {\n      throw StateError('로그인이 필요해요.');\n    }\n    await _authService.ensureFirebaseSessionForKakao(kakaoUserId);`,
  '    final kakaoUserId = await _requireFirebaseReadSession();',
  'callable session requirement'
);
replaceRequired(
  servicePath,
  `    final userId = await _storageService.getKakaoUserId();\n    if (userId == null || userId.isEmpty) {\n      yield const <TeamMeetingRequestDoc>[];\n      return;\n    }`,
  '    final userId = await _requireFirebaseReadSession();',
  'team request stream session'
);
replaceRequired(
  servicePath,
  '  Stream<TeamMeetingRequestDoc?> watchRequest(String requestId) {\n    return _firestore',
  '  Stream<TeamMeetingRequestDoc?> watchRequest(String requestId) async* {\n    await _requireFirebaseReadSession();\n    yield* _firestore',
  'request stream session'
);
replaceRequired(
  servicePath,
  '  Future<TeamMeetingMatchDoc?> getMatchOnce(String matchId) async {\n    final snapshot',
  '  Future<TeamMeetingMatchDoc?> getMatchOnce(String matchId) async {\n    await _requireFirebaseReadSession();\n    final snapshot',
  'match get session'
);
replaceRequired(
  servicePath,
  '  Stream<TeamMeetingMatchDoc?> watchMatch(String matchId) {\n    return _firestore',
  '  Stream<TeamMeetingMatchDoc?> watchMatch(String matchId) async* {\n    await _requireFirebaseReadSession();\n    yield* _firestore',
  'match stream session'
);
replaceRequired(
  servicePath,
  '  Future<TeamMeetingRequestDoc?> getRequestOnce(String requestId) async {\n    final snapshot',
  '  Future<TeamMeetingRequestDoc?> getRequestOnce(String requestId) async {\n    await _requireFirebaseReadSession();\n    final snapshot',
  'request get session'
);
