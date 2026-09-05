import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/friend_invite_service.dart';

/// Client half of the share-invite contract (server half:
/// functions/src/friendInvites.test.ts).
///
/// - The Kakao "친구 추가하기" button resolves to a unique FRIEND_INVITE route;
///   "3:3 미팅 참여하기" to a unique TEAM_INVITE route. Never a homepage, never
///   each other's token.
/// - Incoming links are classified into a typed [PendingInvite]; unknown or
///   contradictory purposes fail closed.
/// - Opening a link never mutates anything: the deep-link handler has no
///   direct acceptFriendInvite call (EXTERNAL_LINK_AUTO_ACCEPT = 0).
/// - No Kakao access-token authentication fallback exists on the client.
void main() {
  const token =
      'a3f1c2d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90';
  const teamToken =
      '0f0e0d0c0b0a09080706050403020100ffeeddccbbaa99887766554433221100';
  final friendPayload = FriendInviteSharePayload(
    inviteId: 'invite_f',
    inviteToken: token,
    inviteUrl: 'https://seolleyeon.com/invite/friend?token=$token',
    deepLinkPath: '/invite/friend',
    expiresAt: DateTime.utc(2026, 9, 10),
    purpose: InvitePurpose.friend,
  );
  final teamPayload = FriendInviteSharePayload(
    inviteId: 'invite_t',
    inviteToken: teamToken,
    inviteUrl: 'https://seolleyeon.com/invite/team?token=$teamToken',
    deepLinkPath: '/invite/team',
    expiresAt: DateTime.utc(2026, 9, 10),
    purpose: InvitePurpose.team,
  );

  group('Kakao friend template', () {
    test('button carries FRIEND execution params and the invite URL', () {
      final template = FriendInviteService.buildKakaoInviteTemplate(
        payload: friendPayload,
        inviterName: '앨리스',
      );

      final button = template.buttons!.single;
      expect(button.title, FriendInviteService.kakaoButtonTitle);
      expect(button.title, '친구 추가하기');
      final link = button.link;
      expect(link.webUrl.toString(), friendPayload.inviteUrl);
      expect(link.mobileWebUrl.toString(), friendPayload.inviteUrl);
      expect(link.androidExecutionParams, {
        'target': 'friend_invite',
        'token': token,
      });
      expect(link.iosExecutionParams, link.androidExecutionParams);
      expect(link.webUrl!.host, 'seolleyeon.com');
      expect(link.webUrl!.path, '/invite/friend');
      expect(template.text, contains('앨리스'));
    });

    test('refuses a TEAM payload', () {
      expect(
        () => FriendInviteService.buildKakaoInviteTemplate(
          payload: teamPayload,
          inviterName: 'x',
        ),
        throwsArgumentError,
      );
    });
  });

  group('Kakao team template', () {
    test('button carries TEAM execution params and the team invite URL', () {
      final template = FriendInviteService.buildKakaoTeamInviteTemplate(
        payload: teamPayload,
        inviterName: '앨리스',
      );

      final button = template.buttons!.single;
      expect(button.title, FriendInviteService.kakaoTeamButtonTitle);
      expect(button.title, '3:3 미팅 참여하기');
      final link = button.link;
      expect(link.webUrl!.host, 'seolleyeon.com');
      expect(link.webUrl!.path, '/invite/team');
      expect(link.webUrl!.queryParameters['token'], teamToken);
      expect(link.androidExecutionParams, {
        'target': 'team_invite',
        'token': teamToken,
      });
      expect(link.iosExecutionParams, link.androidExecutionParams);
      expect(template.text, contains('3:3'));
    });

    test(
      'refuses a FRIEND payload — a team button can never carry a friend token',
      () {
        expect(
          () => FriendInviteService.buildKakaoTeamInviteTemplate(
            payload: friendPayload,
            inviterName: 'x',
          ),
          throwsArgumentError,
        );
      },
    );

    test('friend and team routes are distinct', () {
      expect(
        FriendInviteService.inviteWebPath,
        isNot(FriendInviteService.teamInviteWebPath),
      );
      expect(
        FriendInviteService.inviteTarget,
        isNot(FriendInviteService.teamInviteTarget),
      );
      expect(
        FriendInviteService.kakaoButtonTitle,
        isNot(FriendInviteService.kakaoTeamButtonTitle),
      );
    });
  });

  group('link builder', () {
    test('reads token and purpose back from a URL', () {
      final friend = FriendInviteService.buildKakaoInviteLinkForUrl(
        Uri.parse(friendPayload.inviteUrl),
      );
      expect(friend.androidExecutionParams?['target'], 'friend_invite');
      final team = FriendInviteService.buildKakaoInviteLinkForUrl(
        Uri.parse(teamPayload.inviteUrl),
      );
      expect(team.androidExecutionParams?['target'], 'team_invite');
      expect(team.androidExecutionParams?['token'], teamToken);
    });

    test('refuses URLs without a token or without a purpose path', () {
      expect(
        () => FriendInviteService.buildKakaoInviteLinkForUrl(
          Uri.parse('https://seolleyeon.com/invite/friend'),
        ),
        throwsArgumentError,
      );
      expect(
        () => FriendInviteService.buildKakaoInviteLinkForUrl(
          Uri.parse('https://seolleyeon.com/?token=$token'),
        ),
        throwsArgumentError,
      );
    });

    test('plain Kakao link (non-invite) has no execution params', () {
      final link = FriendInviteService.buildPlainKakaoLink(
        Uri.parse('https://seolleyeon.com'),
      );
      expect(link.androidExecutionParams, isNull);
      expect(link.iosExecutionParams, isNull);
    });
  });

  group('incoming URI → PendingInvite', () {
    PendingInvite? parse(String raw) =>
        FriendInviteService.parseInviteUri(Uri.parse(raw));

    test('friend routes', () {
      final expected = PendingInvite(
        token: token,
        purpose: InvitePurpose.friend,
      );
      expect(
        parse('https://seolleyeon.com/invite/friend?token=$token'),
        expected,
      );
      expect(
        parse('https://seolleyeon-final.web.app/invite/friend?token=$token'),
        expected,
      );
      expect(
        parse('https://seolleyeon.com/invite/friend#token=$token'),
        expected,
      );
      expect(
        parse('seolleyeon://invite/friend?target=friend_invite&token=$token'),
        expected,
      );
      expect(
        parse(
          'kakaocb08e2aea50a58b7d0c5e610e0c5a644://kakaolink?target=friend_invite&token=$token',
        ),
        expected,
      );
    });

    test('team routes', () {
      final expected = PendingInvite(
        token: teamToken,
        purpose: InvitePurpose.team,
      );
      expect(
        parse('https://seolleyeon.com/invite/team?token=$teamToken'),
        expected,
      );
      expect(
        parse('seolleyeon://invite/team?target=team_invite&token=$teamToken'),
        expected,
      );
      expect(
        parse(
          'kakaocb08e2aea50a58b7d0c5e610e0c5a644://kakaolink?target=team_invite&token=$teamToken',
        ),
        expected,
      );
    });

    test('unknown or missing target on the Kakao scheme fails closed', () {
      expect(
        parse('kakaocb08e2aea50a58b7d0c5e610e0c5a644://kakaolink?token=$token'),
        isNull,
      );
      expect(
        parse(
          'kakaocb08e2aea50a58b7d0c5e610e0c5a644://kakaolink?target=foo&token=$token',
        ),
        isNull,
      );
      expect(
        parse('kakaocb08e2aea50a58b7d0c5e610e0c5a644://kakaolink?foo=bar'),
        isNull,
      );
    });

    test('tampered target that contradicts the path fails closed', () {
      expect(
        parse(
          'https://seolleyeon.com/invite/friend?target=team_invite&token=$token',
        ),
        isNull,
      );
      expect(
        parse(
          'https://seolleyeon.com/invite/team?target=friend_invite&token=$teamToken',
        ),
        isNull,
      );
      expect(
        parse('seolleyeon://invite/friend?target=team_invite&token=$token'),
        isNull,
      );
      expect(
        parse('seolleyeon://invite/team?target=friend_invite&token=$teamToken'),
        isNull,
      );
    });

    test('generic homepage and unrelated links are not invites', () {
      for (final raw in [
        'https://seolleyeon.com',
        'https://seolleyeon.com/',
        'https://seolleyeon.com/?token=$token',
        'https://seolleyeon.com/invite/friend',
        'https://seolleyeon.com/invite/team',
        'https://seolleyeon.com/invite/other?token=$token',
        'https://evil.example/invite/friend?token=$token',
        'https://seolleyeon.com/auth/email-link?token=$token',
        'seolleyeon://invite/foo?target=friend_invite&token=$token',
      ]) {
        expect(parse(raw), isNull, reason: raw);
      }
    });
  });

  group('wire formats', () {
    test('purpose round-trips and unknown values are rejected', () {
      for (final purpose in InvitePurpose.values) {
        expect(InvitePurposeWire.fromWire(purpose.wire), purpose);
      }
      expect(InvitePurposeWire.fromWire('friend'), isNull);
      expect(InvitePurposeWire.fromWire(null), isNull);
    });

    test('preview maps server statuses and purpose', () {
      final preview = InvitePreview.fromMap({
        'status': 'valid',
        'purpose': 'TEAM_INVITE',
        'inviterName': '앨리스',
        'teamSetupId': 'team_1',
      });
      expect(preview.isValid, isTrue);
      expect(preview.purpose, InvitePurpose.team);
      expect(preview.teamSetupId, 'team_1');
      expect(
        InvitePreview.fromMap({'status': 'weird'}).status,
        InvitePreviewStatus.invalid,
      );
      expect(
        InvitePreview.fromMap({'status': 'valid', 'purpose': 'ADMIN'}).purpose,
        isNull,
      );
      for (final status in InvitePreviewStatus.values) {
        final p = InvitePreview(status: status);
        expect(p.displayMessage.toLowerCase(), isNot(contains('firebase')));
      }
    });

    test(
      'team redeem result opens the response screen only with an invite id',
      () {
        expect(
          TeamInviteRedeemResult.fromMap({
            'status': 'invited',
            'teamInviteId': 'x',
          }).opensResponseScreen,
          isTrue,
        );
        expect(
          TeamInviteRedeemResult.fromMap({
            'status': 'already_invited',
            'teamInviteId': 'x',
          }).opensResponseScreen,
          isTrue,
        );
        expect(
          TeamInviteRedeemResult.fromMap({
            'status': 'invited',
          }).opensResponseScreen,
          isFalse,
        );
        expect(
          TeamInviteRedeemResult.fromMap({
            'status': 'not_friends',
          }).opensResponseScreen,
          isFalse,
        );
        expect(
          TeamInviteRedeemResult.fromMap({'status': 'not_friends'}).isTerminal,
          isTrue,
        );
        expect(
          TeamInviteRedeemResult.fromMap({'status': 'boom'}).isTerminal,
          isFalse,
        );
        for (final status in TeamInviteRedeemStatus.values) {
          expect(
            TeamInviteRedeemResult(status: status).displayMessage,
            isNotEmpty,
          );
        }
      },
    );

    test('friend accept statuses map to user-facing outcomes', () {
      const terminal = {
        FriendInviteAcceptStatus.accepted,
        FriendInviteAcceptStatus.alreadyFriends,
        FriendInviteAcceptStatus.expired,
        FriendInviteAcceptStatus.invalid,
        FriendInviteAcceptStatus.selfInvite,
        FriendInviteAcceptStatus.blockedRelationship,
      };
      for (final status in FriendInviteAcceptStatus.values) {
        final result = FriendInviteAcceptResult(status: status);
        expect(result.isTerminal, terminal.contains(status), reason: '$status');
        expect(result.displayMessage, isNotEmpty, reason: '$status');
        expect(
          result.displayMessage.toLowerCase(),
          isNot(contains('firebase')),
        );
      }
      expect(
        const FriendInviteAcceptResult(
          status: FriendInviteAcceptStatus.accepted,
          otherUserName: '앨리스',
        ).displayMessage,
        '앨리스과 친구가 되었어요.',
      );
    });
  });

  group('deep-link deduper', () {
    test('same token from a second listener within the window is dropped', () {
      var now = DateTime.utc(2026, 9, 3, 9);
      final deduper = FriendInviteDeepLinkDeduper(
        window: const Duration(seconds: 15),
        now: () => now,
      );
      expect(deduper.shouldProcess(token), isTrue);
      expect(deduper.shouldProcess(token), isFalse);
      now = now.add(const Duration(seconds: 5));
      expect(deduper.shouldProcess(token), isFalse);
      expect(deduper.shouldProcess(teamToken), isTrue);
    });

    test('token is processed again after the window or after release', () {
      var now = DateTime.utc(2026, 9, 3, 9);
      final deduper = FriendInviteDeepLinkDeduper(
        window: const Duration(seconds: 15),
        now: () => now,
      );
      expect(deduper.shouldProcess(token), isTrue);
      now = now.add(const Duration(seconds: 16));
      expect(deduper.shouldProcess(token), isTrue);
      expect(deduper.shouldProcess(token), isFalse);
      deduper.release(token);
      expect(deduper.shouldProcess(token), isTrue);
    });
  });

  group('source scans', () {
    Iterable<File> dartFiles(String root) => Directory(root)
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));

    String norm(String path) => path.replaceAll('\\', '/');

    test(
      'GENERIC_FRIEND_INVITE_LINKS = 0: every Kakao Link is built by FriendInviteService',
      () {
        final offenders = <String>[];
        for (final file in dartFiles('lib')) {
          final path = norm(file.path);
          if (path.endsWith('services/friend_invite_service.dart')) continue;
          if (RegExp(
            r'(^|[^A-Za-z_])Link\(\s*webUrl',
          ).hasMatch(file.readAsStringSync())) {
            offenders.add(path);
          }
        }
        expect(offenders, isEmpty);
      },
    );

    test('TEAM share code never issues a FRIEND invite', () {
      final teamShareFiles = dartFiles('lib').where((f) {
        final p = norm(f.path);
        return p.contains('/event/') || p.contains('team_');
      });
      final offenders = <String>[];
      for (final file in teamShareFiles) {
        final src = file.readAsStringSync();
        if (src.contains('createFriendInvite(') ||
            src.contains('KakaoFriendInviteHelper') ||
            src.contains('createKakaoInvitePayload') ||
            src.contains('createAndShareKakaoInvite') ||
            src.contains('buildKakaoInviteTemplate(') ||
            src.contains('sendFriendInviteMessage(')) {
          offenders.add(norm(file.path));
        }
      }
      expect(
        offenders,
        isEmpty,
        reason: 'team share → createFriendInvite must be 0',
      );
      final teamSetup = File(
        'lib/features/event/screens/team_setup_screen.dart',
      ).readAsStringSync();
      expect(teamSetup, contains('createTeamShareInvite('));
      expect(teamSetup, contains('sendTeamInviteMessage('));
    });

    test(
      'EXTERNAL_LINK_AUTO_ACCEPT = 0: deep-link handlers never accept directly',
      () {
        final authProvider = File(
          'lib/providers/auth_provider.dart',
        ).readAsStringSync();
        final handlerStart = authProvider.indexOf(
          'Future<void> _handleIncomingUri(',
        );
        final handlerEnd = authProvider.indexOf(
          'final link = uri.toString();',
          handlerStart,
        );
        expect(handlerStart, greaterThan(0));
        expect(handlerEnd, greaterThan(handlerStart));
        final handler = authProvider.substring(handlerStart, handlerEnd);
        expect(handler, isNot(contains('acceptFriendInvite(')));
        expect(handler, isNot(contains('redeemTeamShareInvite(')));
        expect(handler, isNot(contains('previewInvite(')));
        expect(handler, contains('parseInviteUri('));
        expect(handler, contains('savePendingInvite('));

        // The only acceptFriendInvite call site in the provider sits behind
        // the confirmation sheet.
        final acceptCalls = 'acceptFriendInvite('
            .allMatches(authProvider)
            .length;
        expect(acceptCalls, 1);
        final confirmIdx = authProvider.indexOf(
          'showFriendInviteConfirmationSheet(',
        );
        final acceptIdx = authProvider.indexOf('acceptFriendInvite(');
        expect(confirmIdx, greaterThan(0));
        expect(acceptIdx, greaterThan(confirmIdx));
        expect(authProvider, contains('if (confirmed != true)'));

        // Team redemption (occupies a pending slot, consumes the token) is
        // likewise behind an explicit tap.
        final redeemCalls = 'redeemTeamShareInvite('
            .allMatches(authProvider)
            .length;
        expect(redeemCalls, 1);
        final teamConfirmIdx = authProvider.indexOf(
          '_confirmTeamInviteOpen(context',
        );
        final redeemIdx = authProvider.indexOf('redeemTeamShareInvite(');
        expect(teamConfirmIdx, greaterThan(0));
        expect(redeemIdx, greaterThan(teamConfirmIdx));
        expect(authProvider, contains('if (proceed != true)'));

        // No other production file accepts friend invites at all.
        for (final file in dartFiles('lib')) {
          final p = norm(file.path);
          if (p.endsWith('providers/auth_provider.dart') ||
              p.endsWith('services/friend_invite_service.dart')) {
            continue;
          }
          expect(
            file.readAsStringSync().contains('acceptFriendInvite('),
            isFalse,
            reason: '$p must not call acceptFriendInvite',
          );
        }
        // The old auto-accept helper is gone.
        expect(
          File('lib/services/friend_invite_service.dart').readAsStringSync(),
          isNot(contains('processPendingInviteIfPossible')),
        );
      },
    );

    test(
      'interrupted confirmation keeps the invite pending; only an explicit decision retires it',
      () {
        final authProvider = File(
          'lib/providers/auth_provider.dart',
        ).readAsStringSync();
        // Friend sheet: null (route reset) → retry, false (나중에) → clear.
        final friendNull = authProvider.indexOf('if (confirmed == null)');
        final friendDecline = authProvider.indexOf('if (confirmed != true)');
        expect(friendNull, greaterThan(0));
        expect(friendDecline, greaterThan(friendNull));
        final friendNullBlock = authProvider.substring(
          friendNull,
          friendDecline,
        );
        expect(friendNullBlock, contains('_scheduleInviteConfirmationRetry()'));
        expect(friendNullBlock, isNot(contains('clearPendingInvite(')));
        expect(friendNullBlock, isNot(contains('acceptFriendInvite(')));
        // Team dialog: same contract.
        final teamNull = authProvider.indexOf('if (proceed == null)');
        final teamDecline = authProvider.indexOf('if (proceed != true)');
        expect(teamNull, greaterThan(0));
        expect(teamDecline, greaterThan(teamNull));
        final teamNullBlock = authProvider.substring(teamNull, teamDecline);
        expect(teamNullBlock, contains('_scheduleInviteConfirmationRetry()'));
        expect(teamNullBlock, isNot(contains('clearPendingInvite(')));
        expect(teamNullBlock, isNot(contains('redeemTeamShareInvite(')));
        // The retry is bounded and only re-enters the routing entry point.
        expect(authProvider, contains('_maxInviteConfirmationRetries'));
        final retryStart = authProvider.indexOf(
          'void _scheduleInviteConfirmationRetry()',
        );
        final retryEnd = authProvider.indexOf(
          'Future<void> resumePendingInvite()',
        );
        final retry = authProvider.substring(retryStart, retryEnd);
        expect(retry, contains('resumePendingInvite()'));
        expect(retry, isNot(contains('acceptFriendInvite(')));
        // The sheet itself cannot be barrier-dismissed, so null is unambiguous.
        final sheet = File(
          'lib/features/profile/widgets/friend_invite_confirmation_sheet.dart',
        ).readAsStringSync();
        expect(sheet, contains('barrierDismissible: false'));
        // The app shell re-presents a pending invite after the splash reset.
        final scaffold = File(
          'lib/shared/layouts/main_scaffold.dart',
        ).readAsStringSync();
        expect(scaffold, contains('resumePendingInvite()'));
        expect(scaffold, isNot(contains('acceptFriendInvite(')));
      },
    );

    test('a preview transport failure never retires a pending invite', () {
      final service = File(
        'lib/services/friend_invite_service.dart',
      ).readAsStringSync();
      final start = service.indexOf('Future<InvitePreview> previewInvite(');
      final end = service.indexOf(
        'Future<FriendInviteAcceptResult> acceptFriendInvite(',
      );
      final preview = service.substring(start, end);
      expect(preview, contains('rethrow'));
      expect(preview, isNot(contains('InvitePreviewStatus.invalid')));
      final authProvider = File(
        'lib/providers/auth_provider.dart',
      ).readAsStringSync();
      final catchIdx = authProvider.indexOf(
        '} on FirebaseFunctionsException catch (e) {',
        authProvider.indexOf('previewInvite(pending.token)'),
      );
      final catchEnd = authProvider.indexOf(
        'final purpose = preview.purpose;',
        catchIdx,
      );
      final catchBlock = authProvider.substring(catchIdx, catchEnd);
      expect(catchBlock, isNot(contains('clearPendingInvite(')));
      expect(catchBlock, contains("e.code == 'unauthenticated'"));
    });

    test('KAKAO_ACCESS_TOKEN_AUTH_FALLBACK = 0 on the invite client', () {
      final service = File(
        'lib/services/friend_invite_service.dart',
      ).readAsStringSync();
      expect(service, isNot(contains('kakaoAccessToken')));
      expect(service, isNot(contains('getKakaoAccessTokenForFunctions')));
      expect(service, contains("httpsCallable('previewInviteToken')"));
      expect(service, contains("httpsCallable('acceptFriendInvite')"));
      expect(service, contains("httpsCallable('redeemEventTeamShareInvite')"));
      expect(service, contains("callableName: 'createEventTeamShareInvite'"));
      expect(service, contains("callableName: 'createFriendInvite'"));
    });

    test(
      'TEAM_CURRENT_KAKAO_AUTH_FALLBACK = 0: team membership client sends no Kakao token',
      () {
        final teamService = File(
          'lib/services/event_team_service.dart',
        ).readAsStringSync();
        expect(teamService, isNot(contains('kakaoAccessToken')));
        expect(teamService, isNot(contains('getKakaoAccessTokenForFunctions')));
        for (final path in [
          'lib/services/team_meeting_request_service.dart',
          'lib/services/event_match_service.dart',
        ]) {
          final src = File(path).readAsStringSync();
          expect(src, isNot(contains('kakaoAccessToken')), reason: path);
          expect(
            src,
            isNot(contains('getKakaoAccessTokenForFunctions')),
            reason: path,
          );
        }
        expect(
          teamService,
          contains("httpsCallable('respondEventTeamInvite')"),
        );
        expect(
          teamService,
          contains('FirebaseAuth.instance.currentUser == null'),
        );

        final index = File('functions/src/index.ts').readAsStringSync();
        for (final name in [
          'ensureEventTeamSetup',
          'createEventTeamInvite',
          'respondEventTeamInvite',
        ]) {
          final start = index.indexOf('export const $name = onCall(');
          expect(start, greaterThan(0), reason: name);
          final end = index.indexOf('\nexport const ', start + 1);
          final body = index.substring(start, end);
          expect(
            body,
            contains('resolveAuthedAppUser(request.auth)'),
            reason: name,
          );
          expect(
            body,
            isNot(contains('resolveUserForFriendCallable')),
            reason: name,
          );
        }
      },
    );

    test('pending invite persistence stores only token + purpose', () {
      final storage = File(
        'lib/services/storage_service.dart',
      ).readAsStringSync();
      expect(storage, contains('savePendingInvitePurpose'));
      final service = File(
        'lib/services/friend_invite_service.dart',
      ).readAsStringSync();
      final persist = service.substring(
        service.indexOf('Future<void> savePendingInvite('),
        service.indexOf('Future<void> clearPendingInvite('),
      );
      expect(persist, isNot(contains('inviterUserId')));
      expect(persist, isNot(contains('inviterName')));
      expect(persist, isNot(contains('email')));
    });
  });
}
