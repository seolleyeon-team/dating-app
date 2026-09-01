import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('recommendation service must not scan users collection as fallback', () {
    final source = File(
      'lib/services/ai_recommendation_service.dart',
    ).readAsStringSync();
    expect(source.contains("_fetchFallbackFromUsers"), isFalse);
    // 금지 대상은 users 컬렉션 자체가 아니라 그 위의 광범위 조회다. 본인
    // 문서 단건 읽기(.doc(uid))는 추천 프라이버시 확인에 필요하므로, 뒤에
    // .doc( 이 오지 않는 사용만 스캔으로 본다.
    final broadUsersAccess = RegExp(
      r"collection\('users'\)\s*(?!\s*\.doc\()",
    ).allMatches(source).map((m) => m.start).toList();
    expect(
      broadUsersAccess,
      isEmpty,
      reason: 'users collection must only be read as .doc(uid), never scanned',
    );
    expect(source.contains('.collection("users")'), isFalse);
    // users collection 참조는 본인 문서 접근(.doc(...))만 허용한다.
    // roster 조회(.where/.limit/.get on collection)는 전체 사용자 노출이므로 금지.
    final usersCollectionUses = RegExp(
      r"collection\('users'\)\s*\.\s*(\w+)\(",
      multiLine: true,
    ).allMatches(source).toList();
    expect(usersCollectionUses, isNotEmpty);
    for (final use in usersCollectionUses) {
      expect(
        use.group(1),
        'doc',
        reason:
            "collection('users') must only be followed by .doc(uid); "
            'roster-level queries are a privacy regression',
      );
    }
    expect(source.contains('_emptyFeedBecauseNoModelRecs'), isTrue);
  });

  test(
    'AI preference screen must not use placeholder or random gender pool',
    () {
      final source = File(
        'lib/features/matching/screens/ai_preference_screen.dart',
      ).readAsStringSync();
      final storageSource = File(
        'lib/features/matching/services/ai_profile_storage_service.dart',
      ).readAsStringSync();
      expect(source.contains('placehold.co'), isFalse);
      expect(source.contains('_addPlaceholderFallbackCards'), isFalse);
      expect(source.contains('refusing random pool fallback'), isTrue);
      expect(source.contains('AiProfileStorageService'), isTrue);
      expect(source.contains('AiPreferenceLoadingCoordinator'), isTrue);
      expect(source.contains('resolveIdentity'), isFalse);
      expect(source.contains('minId: 251'), isFalse);
      expect(source.contains('maxId: 500'), isFalse);
      expect(source.contains('_getDownloadUrl'), isFalse);
      expect(source.contains('targetId: card.identityId'), isTrue);
      expect(source.contains("'shotType': aiPreferenceShotTypeName"), isTrue);
      expect(source.contains('targetId: card.storagePath'), isFalse);
      expect(storageSource.contains('seolleyeon.firebasestorage.app'), isFalse);
      expect(
        storageSource.contains('seolleyeon-final.firebasestorage.app'),
        isTrue,
      );
    },
  );

  test('users collection list must be denied in firestore rules', () {
    final rules = File('firestore.rules').readAsStringSync();
    final usersBlock = RegExp(
      r'match /users/\{kakaoUserId\} \{[\s\S]*?allow list: if ([^;]+);',
    ).firstMatch(rules);
    expect(usersBlock, isNotNull);
    expect(usersBlock!.group(1)!.trim(), 'false');
  });

  test('auth bootstrap must not trust local student-verified flag alone', () {
    final source = File('lib/providers/auth_provider.dart').readAsStringSync();
    expect(
      source.contains('Never trust local SharedPreferences alone'),
      isTrue,
    );
    // A Firebase session without a users doc must clear the local verified
    // flag instead of trusting SharedPreferences.
    expect(
      RegExp(
        r'if \(profile == null\) \{[\s\S]*?'
        r'_isStudentVerified = false;[\s\S]*?'
        r'setStudentVerified\(uid, false\)',
      ).hasMatch(source),
      isTrue,
    );
    // Student verification state always hydrates from the server doc.
    expect(
      source.contains(
        "_isStudentVerified = profile['isStudentVerified'] == true",
      ),
      isTrue,
    );
  });

  test(
    'terms screen and chat list gate fake_user entry behind DevEntryPolicy',
    () {
      final terms = File(
        'lib/features/onboarding/screens/terms_screen.dart',
      ).readAsStringSync();
      final chat = File(
        'lib/features/chat/screens/premium_chat_list_screen.dart',
      ).readAsStringSync();
      expect(terms.contains('DevEntryPolicy.allowTestAccountEntry'), isTrue);
      expect(chat.contains('DevEntryPolicy.allowTestAccountEntry'), isTrue);
    },
  );

  test('ApiService constructor fails closed in release', () {
    final source = File('lib/services/api_service.dart').readAsStringSync();
    expect(source.contains('kReleaseMode'), isTrue);
    expect(source.contains('UnsupportedError'), isTrue);
  });
}
