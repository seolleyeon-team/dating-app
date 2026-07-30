import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Characterization of Storage rules fail-closed posture.
/// Emulator @rules tests remain the runtime source of truth when Java is available.
void main() {
  test('storage.rules deny client writes to private/source/avatar paths', () {
    final rules = File('storage.rules').readAsStringSync();
    expect(rules, contains("match /{allPaths=**}"));
    expect(rules, contains('allow read, write: if false'));
    expect(rules, contains('private_source_photos'));
    expect(rules, contains('avatar_temp'));
    expect(rules, contains('isApprovedAvatarBucket'));
    // Client must not write approved avatars.
    expect(rules, contains('allow write: if false'));
  });
}
