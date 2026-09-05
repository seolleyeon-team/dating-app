import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/friend_invite_service.dart';

/// Native / hosting configuration the friend-invite hand-off depends on.
///
/// KakaoTalk "친구 추가하기" → kakao{NATIVE_APP_KEY}://kakaolink (execution
/// params) or https://seolleyeon.com/invite/friend (App Link / Universal
/// Link) → FriendInviteService.parseInviteUri. If any of these drift the
/// button silently degrades to opening a web page.
void main() {
  final manifest = File(
    'android/app/src/main/AndroidManifest.xml',
  ).readAsStringSync();
  final mainDart = File('lib/main.dart').readAsStringSync();
  final entitlements = File(
    'ios/Runner/Runner.entitlements',
  ).readAsStringSync();
  final infoPlist = File('ios/Runner/Info.plist').readAsStringSync();
  final firebaseJson =
      jsonDecode(File('firebase.json').readAsStringSync())
          as Map<String, dynamic>;
  final serverModule = File(
    'functions/src/friendInvites.ts',
  ).readAsStringSync();

  String nativeAppKey() {
    final match = RegExp(
      r"kakaoNativeAppKey = '([0-9a-f]{32})'",
    ).firstMatch(mainDart);
    expect(
      match,
      isNotNull,
      reason: 'lib/main.dart must define the Kakao native app key',
    );
    return match!.group(1)!;
  }

  group('Android', () {
    test('kakaolink scheme uses the FULL native app key', () {
      final scheme = 'kakao${nativeAppKey()}';
      final filter = RegExp(
        'android:scheme="$scheme"\\s+android:host="kakaolink"',
        multiLine: true,
      );
      expect(
        manifest,
        matches(filter),
        reason: 'MainActivity must accept $scheme://kakaolink',
      );

      // The truncated scheme (missing the "cb" prefix) can never be launched
      // by KakaoTalk and used to be the reason the button fell back to the web.
      final truncated = 'kakao${nativeAppKey().substring(2)}';
      expect(manifest, isNot(contains('android:scheme="$truncated"')));
    });

    test('App Link intent-filters cover the production and legacy hosts', () {
      for (final host in [
        FriendInviteService.inviteWebHost,
        ...FriendInviteService.legacyInviteWebHosts,
      ]) {
        final filter = RegExp(
          '<intent-filter android:autoVerify="true">[\\s\\S]*?android:scheme="https"\\s+android:host="$host"\\s+android:pathPrefix="/invite/friend"',
        );
        expect(manifest, matches(filter), reason: 'missing App Link for $host');
      }
      expect(FriendInviteService.inviteWebHost, 'seolleyeon.com');
    });

    test('team App Link and custom scheme are routed separately from friend', () {
      expect(
        manifest,
        matches(
          RegExp(
            r'<intent-filter android:autoVerify="true">[\s\S]*?android:scheme="https"\s+android:host="seolleyeon.com"\s+android:pathPrefix="/invite/team"',
          ),
        ),
      );
      expect(
        manifest,
        matches(
          RegExp(
            r'android:scheme="seolleyeon"\s+android:host="invite"\s+android:pathPrefix="/team"',
          ),
        ),
      );
    });

    test('intent extras normalisation follows the target (friend vs team)', () {
      final activity = File(
        'android/app/src/main/kotlin/com/seolleyeon/app/MainActivity.kt',
      ).readAsStringSync();
      // invite-*.html intent:// fallback carries S.target / S.token extras.
      expect(activity, contains('getStringExtra("token")'));
      expect(activity, contains('getStringExtra("target")'));
      expect(
        activity,
        contains('if (target == "team_invite") "/team" else "/friend"'),
      );
      expect(activity, isNot(contains('.path("/friend")')));
    });

    test('landing-page custom scheme is still accepted', () {
      expect(
        manifest,
        matches(
          RegExp(
            'android:scheme="seolleyeon"\\s+android:host="invite"\\s+android:pathPrefix="/friend"',
          ),
        ),
      );
    });
  });

  group('iOS', () {
    test('associated domains include the production custom domain', () {
      expect(entitlements, contains('applinks:seolleyeon.com'));
      for (final host in FriendInviteService.legacyInviteWebHosts) {
        expect(entitlements, contains('applinks:$host'));
      }
    });

    test('Kakao custom scheme and app scheme are registered', () {
      expect(infoPlist, contains('<string>kakao${nativeAppKey()}</string>'));
      expect(infoPlist, contains('<string>seolleyeon</string>'));
      final truncated = 'kakao${nativeAppKey().substring(2)}';
      expect(infoPlist, isNot(contains('<string>$truncated</string>')));
    });
  });

  group('Hosting', () {
    test('/invite/friend rewrites to the landing page (token preserved)', () {
      final hosting = firebaseJson['hosting'] as Map<String, dynamic>;
      final rewrites = (hosting['rewrites'] as List)
          .cast<Map<String, dynamic>>();
      expect(
        rewrites.any(
          (r) =>
              r['source'] == '/invite/friend' &&
              r['destination'] == '/invite-friend.html',
        ),
        isTrue,
      );
      final landing = File('public/invite-friend.html').readAsStringSync();
      expect(landing, contains('params.get("token")'));
      expect(
        landing,
        contains('seolleyeon://invite/friend?target=friend_invite&token='),
      );
      expect(landing, contains('package=com.seolleyeon.app'));
    });

    test(
      '/invite/team rewrites to its own landing page with the team scheme',
      () {
        final hosting = firebaseJson['hosting'] as Map<String, dynamic>;
        final rewrites = (hosting['rewrites'] as List)
            .cast<Map<String, dynamic>>();
        expect(
          rewrites.any(
            (r) =>
                r['source'] == '/invite/team' &&
                r['destination'] == '/invite-team.html',
          ),
          isTrue,
        );
        final landing = File('public/invite-team.html').readAsStringSync();
        expect(landing, contains('params.get("token")'));
        expect(
          landing,
          contains('seolleyeon://invite/team?target=team_invite&token='),
        );
        expect(landing, isNot(contains('friend_invite')));
      },
    );

    test('assetlinks and AASA are published for the invite path', () {
      final assetLinks =
          jsonDecode(
                File('public/.well-known/assetlinks.json').readAsStringSync(),
              )
              as List;
      final target = (assetLinks.first as Map)['target'] as Map;
      expect(target['package_name'], 'com.seolleyeon.app');
      expect((target['sha256_cert_fingerprints'] as List), isNotEmpty);

      final aasa =
          jsonDecode(
                File(
                  'public/.well-known/apple-app-site-association',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      final details =
          ((aasa['applinks'] as Map)['details'] as List).first as Map;
      expect(
        (details['paths'] as List),
        containsAll([
          '/invite/friend',
          '/invite/friend/*',
          '/invite/team',
          '/invite/team/*',
        ]),
      );
    });
  });

  group('server ↔ client contract', () {
    test(
      'server issues invite URLs on the same host the client recognises',
      () {
        expect(
          serverModule,
          contains(
            'FRIEND_INVITE_HOST = "${FriendInviteService.inviteWebHost}"',
          ),
        );
        expect(
          serverModule,
          contains(
            'FRIEND_INVITE_PATH = "${FriendInviteService.inviteWebPath}"',
          ),
        );
        expect(
          serverModule,
          contains(
            'FRIEND_INVITE_TARGET = "${FriendInviteService.inviteTarget}"',
          ),
        );
        expect(
          serverModule,
          contains(
            'TEAM_INVITE_PATH = "${FriendInviteService.teamInviteWebPath}"',
          ),
        );
        expect(
          serverModule,
          contains(
            'TEAM_INVITE_TARGET = "${FriendInviteService.teamInviteTarget}"',
          ),
        );
        for (final host in FriendInviteService.legacyInviteWebHosts) {
          expect(serverModule, contains('"$host"'));
        }
      },
    );
  });
}
