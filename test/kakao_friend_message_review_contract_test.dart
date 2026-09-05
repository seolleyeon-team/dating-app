import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:kakao_flutter_sdk_talk/kakao_flutter_sdk_talk.dart';
import 'package:seolleyeon/services/kakao_talk_friend_service.dart';

void main() {
  group('Kakao review consent status', () {
    test('distinguishes console usage from user agreement', () {
      final status = KakaoConsentStatus.fromScopes(
        userId: 123456789,
        scopes: [
          Scope(
            KakaoTalkFriendService.friendsScope,
            '친구목록',
            ScopeType.service,
            true,
            null,
            true,
            true,
          ),
          Scope(
            KakaoTalkFriendService.talkMessageScope,
            '메시지',
            ScopeType.service,
            true,
            null,
            false,
            true,
          ),
        ],
      );

      expect(status.userId, 123456789);
      expect(status.friendsUsing, isTrue);
      expect(status.friendsAgreed, isTrue);
      expect(status.talkMessageUsing, isTrue);
      expect(status.talkMessageAgreed, isFalse);
    });

    test('missing review scopes are neither enabled nor agreed', () {
      final status = KakaoConsentStatus.fromScopes(
        userId: null,
        scopes: const <Scope>[],
      );

      expect(status.friendsUsing, isFalse);
      expect(status.friendsAgreed, isFalse);
      expect(status.talkMessageUsing, isFalse);
      expect(status.talkMessageAgreed, isFalse);
    });
  });

  test('active review flows call Kakao Friend and Message APIs', () {
    final serviceSource = File(
      'lib/services/kakao_talk_friend_service.dart',
    ).readAsStringSync();
    final teamSetupSource = File(
      'lib/features/event/screens/team_setup_screen.dart',
    ).readAsStringSync();
    final routerSource = File('lib/router/app_router.dart').readAsStringSync();

    expect(serviceSource, contains('TalkApi.instance.friends('));
    expect(serviceSource, contains('TalkApi.instance.sendDefaultMemo('));
    expect(serviceSource, contains('TalkApi.instance.sendDefaultMessage('));
    expect(
      serviceSource,
      contains('ensureRequiredConsents(requireTalkMessage: true)'),
    );
    expect(teamSetupSource, contains('_kakaoFriendService.fetchFriends()'));
    expect(
      teamSetupSource,
      contains('_kakaoFriendService.sendTeamInviteMessage('),
    );
    expect(routerSource, contains('case RouteNames.kakaoFriendMessageTest:'));
  });

  test('friend consent flow does not request the current Kakao profile', () {
    final source = File(
      'lib/services/kakao_talk_friend_service.dart',
    ).readAsStringSync();
    final start = source.indexOf(
      'Future<KakaoConsentStatus> ensureRequiredConsents',
    );
    final end = source.indexOf(
      'Future<KakaoTalkFriendLookupResult> fetchFriends',
      start,
    );
    expect(start, isNonNegative);
    expect(end, greaterThan(start));
    final section = source.substring(start, end);

    expect(section, contains('loginWithNewScopes(missingScopes)'));
    expect(section, isNot(contains('fetchCurrentUser()')));
  });
}
