import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('Kakao login does not read or submit a phone number', () {
    final source = _read('lib/services/auth_service.dart');

    expect(source, isNot(contains('kakaoAccount?.phoneNumber')));
    expect(source, isNot(contains('saveUserPhoneHash')));
    expect(source, isNot(contains('PhoneHashUtils')));
  });

  test('device contacts are hashed locally and matched only on the server', () {
    final client = _read('lib/services/contact_block_service.dart');
    final server = _read('functions/src/index.ts');

    expect(client, contains('PhoneHashUtils.normalizeAndHash(phone.number)'));
    expect(client, contains("httpsCallable('syncContactBlocks')"));
    expect(server, contains('const VERIFIED_PHONE_HASH_INDEX'));
    expect(server, contains('collection("userPrivateVerifications")'));
    expect(server, contains('matchSource: "kg_inicis_verified_phone"'));
  });

  test(
    'verified phone matches feed the existing block-based recommendation filter',
    () {
      final recommendation = _read(
        'lib/services/ai_recommendation_service.dart',
      );
      final rules = _read('firestore.rules');
      final contactScreen = _read(
        'lib/features/profile/screens/contact_block_screen.dart',
      );

      expect(recommendation, contains("collection('blocks')"));
      expect(rules, contains('match /userPrivateVerifications/{uid}'));
      expect(rules, contains('match /verifiedPhoneHashIndex/{phoneHash}'));
      expect(rules, contains('allow read, write: if false;'));
      expect(contactScreen, contains('KG이니시스 본인인증을 완료한 가입자 정보와만 대조돼요.'));
    },
  );
}
