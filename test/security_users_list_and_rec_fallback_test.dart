import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('recommendation service must not scan users collection as fallback', () {
    final source = File(
      'lib/services/ai_recommendation_service.dart',
    ).readAsStringSync();
    expect(source.contains("_fetchFallbackFromUsers"), isFalse);
    expect(source.contains("collection('users')"), isFalse);
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
    // Missing Firestore user doc path must clear local verified flag.
    expect(
      RegExp(
        r'kakaoUserExists[\s\S]*?else \{[\s\S]*?'
        r'_isStudentVerified = false;[\s\S]*?'
        r'setStudentVerified\(kakaoUserId, false\)',
      ).hasMatch(source),
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
