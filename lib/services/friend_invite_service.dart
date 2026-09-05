import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart'
    show TargetPlatform, debugPrint, defaultTargetPlatform, kIsWeb;
import 'package:flutter/services.dart';
import 'package:kakao_flutter_sdk_share/kakao_flutter_sdk_share.dart';
import 'package:url_launcher/url_launcher.dart';

import 'auth_service.dart';
import 'storage_service.dart';
import '../shared/utils/privacy_log_utils.dart';

// =============================================================================
// Share-link invitations (friend / 3:3 team)
//
// A share link carries ONLY an opaque token plus a routing hint
// (`target=friend_invite` / `target=team_invite`, or the /invite/friend vs
// /invite/team path). The hint decides which screen the app opens; the
// server record's `purpose` (returned by previewInviteToken) decides what the
// token may do. Nothing in this file mutates the friend graph without an
// explicit in-app confirmation followed by acceptFriendInvite.
//
// AUTH CONTRACT: every callable here requires a Firebase-authenticated
// canonical app session. There is no Kakao access-token fallback.
// =============================================================================

/// Routing purpose of a share link. Mirrors the server's invite `purpose`.
enum InvitePurpose { friend, team }

extension InvitePurposeWire on InvitePurpose {
  /// Value persisted locally and matched against the server preview.
  String get wire => switch (this) {
    InvitePurpose.friend => 'FRIEND_INVITE',
    InvitePurpose.team => 'TEAM_INVITE',
  };

  /// Kakao execution-param / custom-scheme `target` value.
  String get target => switch (this) {
    InvitePurpose.friend => FriendInviteService.inviteTarget,
    InvitePurpose.team => FriendInviteService.teamInviteTarget,
  };

  static InvitePurpose? fromWire(String? raw) {
    switch (raw) {
      case 'FRIEND_INVITE':
        return InvitePurpose.friend;
      case 'TEAM_INVITE':
        return InvitePurpose.team;
      default:
        return null;
    }
  }
}

/// A share link the app received but has not acted on yet. Only the opaque
/// token and the routing purpose are kept — never inviter identity.
class PendingInvite {
  final String token;
  final InvitePurpose purpose;

  const PendingInvite({required this.token, required this.purpose});

  @override
  bool operator ==(Object other) =>
      other is PendingInvite &&
      other.token == token &&
      other.purpose == purpose;

  @override
  int get hashCode => Object.hash(token, purpose);

  @override
  String toString() => 'PendingInvite(purpose: ${purpose.name})';
}

enum InvitePreviewStatus {
  valid,
  invalid,
  expired,
  used,
  selfInvite,
  alreadyFriends,
}

/// What the confirmation UI shows before any mutation. The [purpose] is the
/// server's, and is the only value the app routes on after preview.
class InvitePreview {
  final InvitePreviewStatus status;
  final InvitePurpose? purpose;
  final String? message;
  final String? inviterUserId;
  final String? inviterName;
  final String? inviterImageUrl;
  final String? teamSetupId;

  const InvitePreview({
    required this.status,
    this.purpose,
    this.message,
    this.inviterUserId,
    this.inviterName,
    this.inviterImageUrl,
    this.teamSetupId,
  });

  bool get isValid => status == InvitePreviewStatus.valid;

  factory InvitePreview.fromMap(Map<String, dynamic> data) {
    final status = switch (data['status']?.toString()) {
      'valid' => InvitePreviewStatus.valid,
      'expired' => InvitePreviewStatus.expired,
      'used' => InvitePreviewStatus.used,
      'self_invite' => InvitePreviewStatus.selfInvite,
      'already_friends' => InvitePreviewStatus.alreadyFriends,
      _ => InvitePreviewStatus.invalid,
    };
    return InvitePreview(
      status: status,
      purpose: InvitePurposeWire.fromWire(data['purpose']?.toString()),
      message: data['message']?.toString(),
      inviterUserId: data['inviterUserId']?.toString(),
      inviterName: data['inviterName']?.toString(),
      inviterImageUrl: data['inviterImageUrl']?.toString(),
      teamSetupId: data['teamSetupId']?.toString(),
    );
  }

  String get displayMessage {
    final m = message?.trim();
    if (m != null && m.isNotEmpty) return m;
    return switch (status) {
      InvitePreviewStatus.valid => '',
      InvitePreviewStatus.invalid => '유효하지 않은 초대 링크예요.',
      InvitePreviewStatus.expired => '초대 링크가 만료되었어요.',
      InvitePreviewStatus.used => '이미 사용된 초대 링크예요.',
      InvitePreviewStatus.selfInvite => '내가 만든 초대 링크는 사용할 수 없어요.',
      InvitePreviewStatus.alreadyFriends => '이미 친구로 연결되어 있어요.',
    };
  }
}

enum FriendInviteAcceptStatus {
  accepted,
  alreadyFriends,
  expired,
  invalid,
  selfInvite,
  blockedRelationship,
  pendingLogin,
  pendingVerification,
  error,
}

/// Collapses the same invite token arriving through several deep-link
/// listeners (app_links cold start, app_links stream, and the Kakao SDK scheme
/// stream all observe one KakaoTalk hand-off) into a single handling.
///
/// Pure and injectable so the policy is unit-testable without Firebase.
class FriendInviteDeepLinkDeduper {
  FriendInviteDeepLinkDeduper({
    this.window = const Duration(seconds: 15),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Duration window;
  final DateTime Function() _now;
  final Map<String, DateTime> _seenAt = <String, DateTime>{};

  /// Returns true when [token] should be processed, false when the same token
  /// was already accepted for processing inside [window].
  bool shouldProcess(String token) {
    final now = _now();
    _seenAt.removeWhere((_, seen) => now.difference(seen) > window);
    final previous = _seenAt[token];
    if (previous != null) return false;
    _seenAt[token] = now;
    return true;
  }

  /// Forget a token so a later, genuinely new hand-off is processed again
  /// (used after a non-terminal result such as "login first").
  void release(String token) {
    _seenAt.remove(token);
  }
}

enum FriendInviteShareSurface { kakaoTalkApp, webSharePage, desktopSharePage }

class FriendInviteShareResult {
  final FriendInviteShareSurface surface;
  final bool inviteLinkCopied;

  const FriendInviteShareResult({
    required this.surface,
    this.inviteLinkCopied = false,
  });

  String get successMessage {
    switch (surface) {
      case FriendInviteShareSurface.kakaoTalkApp:
        return '카카오톡 공유 화면을 열었어요.';
      case FriendInviteShareSurface.webSharePage:
        return '카카오 공유 페이지를 열었어요.';
      case FriendInviteShareSurface.desktopSharePage:
        return inviteLinkCopied
            ? '데스크톱에서 카카오 공유 페이지를 열고 초대 링크를 복사했어요.'
            : '데스크톱에서 카카오 공유 페이지를 열었어요.';
    }
  }
}

/// A server-issued share link (friend or team). The token is opaque.
class FriendInviteSharePayload {
  final String inviteId;
  final String inviteToken;
  final String inviteUrl;
  final String deepLinkPath;
  final DateTime? expiresAt;
  final InvitePurpose purpose;

  const FriendInviteSharePayload({
    required this.inviteId,
    required this.inviteToken,
    required this.inviteUrl,
    required this.deepLinkPath,
    required this.expiresAt,
    this.purpose = InvitePurpose.friend,
  });

  factory FriendInviteSharePayload.fromMap(
    Map<String, dynamic> data, {
    InvitePurpose fallbackPurpose = InvitePurpose.friend,
  }) {
    return FriendInviteSharePayload(
      inviteId: data['inviteId']?.toString() ?? '',
      inviteToken: data['inviteToken']?.toString() ?? '',
      inviteUrl: data['inviteUrl']?.toString() ?? '',
      deepLinkPath: data['deepLinkPath']?.toString() ?? '/invite/friend',
      expiresAt: DateTime.tryParse(data['expiresAt']?.toString() ?? ''),
      purpose:
          InvitePurposeWire.fromWire(data['purpose']?.toString()) ??
          fallbackPurpose,
    );
  }
}

class FriendInviteAcceptResult {
  final FriendInviteAcceptStatus status;
  final String? pairId;
  final String? otherUserId;
  final String? otherUserName;
  final String? message;

  const FriendInviteAcceptResult({
    required this.status,
    this.pairId,
    this.otherUserId,
    this.otherUserName,
    this.message,
  });

  bool get isSuccessLike =>
      status == FriendInviteAcceptStatus.accepted ||
      status == FriendInviteAcceptStatus.alreadyFriends;

  bool get isTerminal =>
      status != FriendInviteAcceptStatus.pendingLogin &&
      status != FriendInviteAcceptStatus.pendingVerification &&
      status != FriendInviteAcceptStatus.error;

  String get displayMessage {
    if (message != null && message!.trim().isNotEmpty) {
      return message!.trim();
    }

    switch (status) {
      case FriendInviteAcceptStatus.accepted:
        final name = otherUserName?.trim();
        return (name != null && name.isNotEmpty)
            ? '$name과 친구가 되었어요.'
            : '친구가 추가되었어요.';
      case FriendInviteAcceptStatus.alreadyFriends:
        final name = otherUserName?.trim();
        return (name != null && name.isNotEmpty)
            ? '$name님과 이미 친구예요.'
            : '이미 친구로 연결되어 있어요.';
      case FriendInviteAcceptStatus.expired:
        return '친구 초대 링크가 만료되었어요.';
      case FriendInviteAcceptStatus.invalid:
        return '유효하지 않은 친구 초대 링크예요.';
      case FriendInviteAcceptStatus.selfInvite:
        return '내가 만든 초대 링크로는 친구를 추가할 수 없어요.';
      case FriendInviteAcceptStatus.blockedRelationship:
        return '지금은 이 사용자와 친구를 맺을 수 없어요.';
      case FriendInviteAcceptStatus.pendingLogin:
        return '로그인하면 친구 초대를 이어서 확인할 수 있어요.';
      case FriendInviteAcceptStatus.pendingVerification:
        return '학교 이메일 인증을 마치면 친구 초대를 이어서 확인할 수 있어요.';
      case FriendInviteAcceptStatus.error:
        return '친구 초대를 처리하지 못했어요. 잠시 후 다시 시도해주세요.';
    }
  }
}

enum TeamInviteRedeemStatus {
  invited,
  alreadyInvited,
  alreadyMember,
  notFriends,
  teamFull,
  teamMissing,
  expired,
  invalid,
  selfInvite,
  blocked,
  error,
}

class TeamInviteRedeemResult {
  final TeamInviteRedeemStatus status;
  final String? teamInviteId;
  final String? teamSetupId;
  final String? inviterName;
  final String? message;

  const TeamInviteRedeemResult({
    required this.status,
    this.teamInviteId,
    this.teamSetupId,
    this.inviterName,
    this.message,
  });

  /// The canonical team invitation exists; open the existing response screen.
  bool get opensResponseScreen =>
      (status == TeamInviteRedeemStatus.invited ||
          status == TeamInviteRedeemStatus.alreadyInvited) &&
      (teamInviteId?.isNotEmpty ?? false);

  bool get isTerminal => status != TeamInviteRedeemStatus.error;

  factory TeamInviteRedeemResult.fromMap(Map<String, dynamic> data) {
    final status = switch (data['status']?.toString()) {
      'invited' => TeamInviteRedeemStatus.invited,
      'already_invited' => TeamInviteRedeemStatus.alreadyInvited,
      'already_member' => TeamInviteRedeemStatus.alreadyMember,
      'not_friends' => TeamInviteRedeemStatus.notFriends,
      'team_full' => TeamInviteRedeemStatus.teamFull,
      'team_missing' => TeamInviteRedeemStatus.teamMissing,
      'expired' => TeamInviteRedeemStatus.expired,
      'invalid' => TeamInviteRedeemStatus.invalid,
      'self_invite' => TeamInviteRedeemStatus.selfInvite,
      'blocked' => TeamInviteRedeemStatus.blocked,
      _ => TeamInviteRedeemStatus.error,
    };
    return TeamInviteRedeemResult(
      status: status,
      teamInviteId: data['teamInviteId']?.toString(),
      teamSetupId: data['teamSetupId']?.toString(),
      inviterName: data['inviterName']?.toString(),
      message: data['message']?.toString(),
    );
  }

  String get displayMessage {
    final m = message?.trim();
    if (m != null && m.isNotEmpty) return m;
    final name = inviterName?.trim();
    return switch (status) {
      TeamInviteRedeemStatus.invited || TeamInviteRedeemStatus.alreadyInvited =>
        (name != null && name.isNotEmpty)
            ? '$name님의 3:3 팀 초대를 확인해주세요.'
            : '3:3 팀 초대를 확인해주세요.',
      TeamInviteRedeemStatus.alreadyMember => '이미 이 팀에 참여하고 있어요.',
      TeamInviteRedeemStatus.notFriends => '먼저 초대한 사람과 친구로 연결되어야 팀에 참여할 수 있어요.',
      TeamInviteRedeemStatus.teamFull => '팀 정원이 찼어요.',
      TeamInviteRedeemStatus.teamMissing => '팀 정보를 찾을 수 없어요.',
      TeamInviteRedeemStatus.expired => '3:3 팀 초대 링크가 만료되었어요.',
      TeamInviteRedeemStatus.invalid => '유효하지 않은 3:3 팀 초대 링크예요.',
      TeamInviteRedeemStatus.selfInvite => '내가 만든 초대 링크는 사용할 수 없어요.',
      TeamInviteRedeemStatus.blocked => '지금은 이 사용자와 함께할 수 없어요.',
      TeamInviteRedeemStatus.error => '팀 초대를 처리하지 못했어요. 잠시 후 다시 시도해주세요.',
    };
  }
}

class FriendInviteService {
  FriendInviteService({
    FirebaseFunctions? functions,
    StorageService? storageService,
    AuthService? authService,
  }) : _functions =
           functions ?? FirebaseFunctions.instanceFor(region: _functionsRegion),
       _storageService = storageService ?? StorageService(),
       _authService = authService ?? AuthService();

  static const String _functionsRegion = 'asia-northeast3';

  /// Production custom domain of the Firebase Hosting site. Must match
  /// `FRIEND_INVITE_HOST` in functions/src/friendInvites.ts, the Android App
  /// Link intent-filters, and the iOS associated domain.
  static const String inviteWebHost = 'seolleyeon.com';

  /// Hosts that previously issued invite links resolve on. Still recognised so
  /// links shared before the domain switch keep working.
  static const Set<String> legacyInviteWebHosts = {'seolleyeon-final.web.app'};
  static const String inviteWebPath = '/invite/friend';
  static const String teamInviteWebPath = '/invite/team';
  static const String inviteScheme = 'seolleyeon';
  static const String inviteTarget = 'friend_invite';
  static const String teamInviteTarget = 'team_invite';
  static const String kakaoLinkHost = 'kakaolink';
  static const String kakaoButtonTitle = '친구 추가하기';
  static const String kakaoTeamButtonTitle = '3:3 미팅 참여하기';

  final FirebaseFunctions _functions;
  final StorageService _storageService;
  final AuthService _authService;

  bool get _isDesktopPlatform =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.windows ||
          defaultTargetPlatform == TargetPlatform.macOS ||
          defaultTargetPlatform == TargetPlatform.linux);

  // ---------------------------------------------------------------------------
  // Kakao link / template builders (the only place a Kakao `Link` is built)
  // ---------------------------------------------------------------------------

  /// A Kakao `Link` for a share invite. The execution params make KakaoTalk
  /// launch the installed app through
  /// `kakao{NATIVE_APP_KEY}://kakaolink?target=<purpose>&token=...`; the web
  /// URLs are the fallback for devices without the app.
  static Link buildKakaoInviteLink(FriendInviteSharePayload payload) {
    return buildKakaoInviteLinkForUrl(
      Uri.parse(payload.inviteUrl),
      token: payload.inviteToken,
      purpose: payload.purpose,
    );
  }

  /// Same as [buildKakaoInviteLink] for callers that only hold the URL
  /// (Kakao Message API). The token and purpose are read back from the URL
  /// when omitted.
  static Link buildKakaoInviteLinkForUrl(
    Uri inviteUri, {
    String? token,
    InvitePurpose? purpose,
  }) {
    final resolvedToken = (token != null && token.trim().isNotEmpty)
        ? token.trim()
        : _extractInviteTokenFromUri(inviteUri);
    if (resolvedToken == null || resolvedToken.isEmpty) {
      throw ArgumentError('invite link without a token');
    }
    final resolvedPurpose = purpose ?? _purposeFromPath(inviteUri.path);
    if (resolvedPurpose == null) {
      throw ArgumentError('invite link without a recognised purpose path');
    }
    final executionParams = <String, String>{
      'target': resolvedPurpose.target,
      'token': resolvedToken,
    };
    return Link(
      webUrl: inviteUri,
      mobileWebUrl: inviteUri,
      androidExecutionParams: executionParams,
      iosExecutionParams: executionParams,
    );
  }

  /// A Kakao link that is NOT an invite (e.g. Message API self-test).
  static Link buildPlainKakaoLink(Uri uri) {
    return Link(webUrl: uri, mobileWebUrl: uri);
  }

  /// The KakaoTalk friend-invite message. The "친구 추가하기" button always
  /// points at a unique FRIEND_INVITE token.
  static TextTemplate buildKakaoInviteTemplate({
    required FriendInviteSharePayload payload,
    required String inviterName,
  }) {
    if (payload.purpose != InvitePurpose.friend) {
      throw ArgumentError('friend template requires a FRIEND_INVITE payload');
    }
    final link = buildKakaoInviteLink(payload);
    return TextTemplate(
      text: '설레연에서 친구 추가하기\n${_shareDisplayName(inviterName)}님이 친구로 초대했어요.',
      link: link,
      buttons: [Button(title: kakaoButtonTitle, link: link)],
      buttonTitle: kakaoButtonTitle,
    );
  }

  /// The KakaoTalk 3:3 team message. The "3:3 미팅 참여하기" button always
  /// points at a unique TEAM_INVITE token — never at a friend invite.
  static TextTemplate buildKakaoTeamInviteTemplate({
    required FriendInviteSharePayload payload,
    required String inviterName,
  }) {
    if (payload.purpose != InvitePurpose.team) {
      throw ArgumentError('team template requires a TEAM_INVITE payload');
    }
    final link = buildKakaoInviteLink(payload);
    return TextTemplate(
      text: '${_shareDisplayName(inviterName)}님이 설레연 3:3 미팅 팀에 함께 참여하자고 초대했어요.',
      link: link,
      buttons: [Button(title: kakaoTeamButtonTitle, link: link)],
      buttonTitle: kakaoTeamButtonTitle,
    );
  }

  // ---------------------------------------------------------------------------
  // Issue
  // ---------------------------------------------------------------------------

  Future<FriendInviteSharePayload> createFriendInvite() async {
    return _createInvite(
      callableName: 'createFriendInvite',
      data: const {'shareChannel': 'kakaotalk'},
      purpose: InvitePurpose.friend,
      logTag: 'createFriendInvite',
    );
  }

  /// Leader-only 3:3 team share link (server-validated).
  Future<FriendInviteSharePayload> createTeamShareInvite({
    required String teamSetupId,
  }) async {
    return _createInvite(
      callableName: 'createEventTeamShareInvite',
      data: {'teamSetupId': teamSetupId, 'shareChannel': 'kakaotalk'},
      purpose: InvitePurpose.team,
      logTag: 'createTeamShareInvite',
    );
  }

  Future<FriendInviteSharePayload> _createInvite({
    required String callableName,
    required Map<String, dynamic> data,
    required InvitePurpose purpose,
    required String logTag,
  }) async {
    try {
      debugPrint('[FriendInvite] $logTag start');
      await _requireCanonicalSession();

      final callable = _functions.httpsCallable(callableName);
      final result = await callable.call(data);
      final map = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final payload = FriendInviteSharePayload.fromMap(
        map,
        fallbackPurpose: purpose,
      );

      if (payload.inviteId.isEmpty ||
          payload.inviteToken.isEmpty ||
          payload.inviteUrl.isEmpty ||
          payload.purpose != purpose) {
        throw Exception('초대 응답이 올바르지 않아요.');
      }

      debugPrint(
        '[FriendInvite] $logTag success '
        '${PrivacyLogUtils.idFingerprint(payload.inviteId)} '
        '${PrivacyLogUtils.pathFingerprint(payload.inviteUrl)}',
      );
      return payload;
    } on FirebaseFunctionsException catch (e) {
      debugPrint('[FriendInvite] $logTag ${PrivacyLogUtils.errorSummary(e)}');
      throw Exception(_functionsErrorMessage(e));
    } catch (e) {
      debugPrint('[FriendInvite] $logTag ${PrivacyLogUtils.errorSummary(e)}');
      throw Exception('초대 링크를 만들지 못했어요: $e');
    }
  }

  /// Every invite callable needs the Firebase canonical session. A cached
  /// local id or a Kakao SDK session is NOT enough (and is never sent).
  Future<void> _requireCanonicalSession() async {
    final appUserId = await _storageService.getAppUserId();
    if (appUserId == null || appUserId.isEmpty) {
      throw Exception('로그인이 필요해요.');
    }
    final attached = await _authService.ensureCanonicalAppSession();
    debugPrint(
      '[FriendInvite] canonical session attached=$attached '
      '${PrivacyLogUtils.idFingerprint(FirebaseAuth.instance.currentUser?.uid)}',
    );
    if (FirebaseAuth.instance.currentUser == null) {
      throw Exception('로그인이 필요해요. 연세 메일 로그인 후 다시 시도해주세요.');
    }
  }

  bool get hasCanonicalFirebaseSession =>
      FirebaseAuth.instance.currentUser != null;

  // ---------------------------------------------------------------------------
  // Share
  // ---------------------------------------------------------------------------

  Future<FriendInviteShareResult> shareInviteViaKakao({
    required FriendInviteSharePayload payload,
    required String inviterName,
  }) {
    final template = payload.purpose == InvitePurpose.team
        ? buildKakaoTeamInviteTemplate(
            payload: payload,
            inviterName: inviterName,
          )
        : buildKakaoInviteTemplate(payload: payload, inviterName: inviterName);
    return shareTemplateViaKakao(
      template: template,
      inviteUrl: payload.inviteUrl,
    );
  }

  Future<FriendInviteShareResult> shareTemplateViaKakao({
    required TextTemplate template,
    required String inviteUrl,
  }) async {
    debugPrint(
      '[FriendInvite] share target ${PrivacyLogUtils.pathFingerprint(inviteUrl)}',
    );

    try {
      debugPrint(
        "[FriendInvite] shareTemplateViaKakao start platform=${kIsWeb ? 'web' : 'native'}",
      );

      if (kIsWeb) {
        final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
          template: template,
        );
        final launched = await launchUrl(sharerUri, webOnlyWindowName: '_self');
        if (!launched) {
          throw Exception('카카오 공유 페이지를 열지 못했어요.');
        }
        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.webSharePage,
        );
      }

      if (_isDesktopPlatform) {
        final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
          template: template,
        );
        await Clipboard.setData(ClipboardData(text: inviteUrl));
        final launched = await launchUrl(
          sharerUri,
          mode: LaunchMode.externalApplication,
        );
        if (!launched) {
          throw Exception('데스크톱에서 카카오 공유 페이지를 열지 못했어요.');
        }
        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.desktopSharePage,
          inviteLinkCopied: true,
        );
      }

      final canShareToTalk = await ShareClient.instance
          .isKakaoTalkSharingAvailable();
      debugPrint('[FriendInvite] KakaoTalk available=$canShareToTalk');

      if (canShareToTalk) {
        final sharingUri = await ShareClient.instance.shareDefault(
          template: template,
        );
        await ShareClient.instance.launchKakaoTalk(sharingUri);
        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.kakaoTalkApp,
        );
      }

      final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
        template: template,
      );
      final launched = await launchUrl(
        sharerUri,
        mode: LaunchMode.externalApplication,
      );
      if (!launched) {
        throw Exception('카카오 공유 페이지를 열지 못했어요.');
      }
      return const FriendInviteShareResult(
        surface: FriendInviteShareSurface.webSharePage,
      );
    } catch (e) {
      debugPrint(
        '[FriendInvite] shareTemplateViaKakao ${PrivacyLogUtils.errorSummary(e)}',
      );
      throw Exception('카카오톡 공유를 실행하지 못했어요: $e');
    }
  }

  // ---------------------------------------------------------------------------
  // Incoming link classification (routing hints only — never authorization)
  // ---------------------------------------------------------------------------

  /// Parses an incoming URI into a [PendingInvite], or null when the URI is
  /// not a share invite. Unknown `target` values fail closed.
  static PendingInvite? parseInviteUri(Uri uri) {
    final token = _extractInviteTokenFromUri(uri);
    if (token == null || token.isEmpty) return null;

    final normalizedPath = uri.path.toLowerCase();
    final normalizedHost = uri.host.toLowerCase();
    final scheme = uri.scheme.toLowerCase();
    final target = uri.queryParameters['target'];
    final purposeFromTarget = _purposeFromTarget(target);

    // Kakao execution params: kakao{key}://kakaolink?target=...&token=...
    if (normalizedHost == kakaoLinkHost && scheme.startsWith('kakao')) {
      return purposeFromTarget == null
          ? null
          : PendingInvite(token: token, purpose: purposeFromTarget);
    }

    // Landing-page custom scheme: seolleyeon://invite/friend | /team
    if (scheme == inviteScheme) {
      InvitePurpose? purposeFromPath;
      if (normalizedHost == 'invite') {
        purposeFromPath = switch (normalizedPath) {
          '/friend' => InvitePurpose.friend,
          '/team' => InvitePurpose.team,
          _ => null,
        };
      } else {
        purposeFromPath = _purposeFromPath(normalizedPath);
      }
      return _resolvePurpose(token, purposeFromPath, purposeFromTarget);
    }

    // HTTPS App Link / Universal Link on the production or legacy host.
    final isWebLink =
        (scheme == 'https' || scheme == 'http') &&
        (normalizedHost == inviteWebHost ||
            legacyInviteWebHosts.contains(normalizedHost));
    if (!isWebLink) return null;

    return _resolvePurpose(
      token,
      _purposeFromPath(normalizedPath),
      purposeFromTarget,
    );
  }

  static PendingInvite? _resolvePurpose(
    String token,
    InvitePurpose? fromPath,
    InvitePurpose? fromTarget,
  ) {
    if (fromPath == null) return null;
    // A target that contradicts the path is a tampered link: fail closed.
    if (fromTarget != null && fromTarget != fromPath) return null;
    return PendingInvite(token: token, purpose: fromPath);
  }

  static InvitePurpose? _purposeFromTarget(String? target) {
    return switch (target) {
      inviteTarget => InvitePurpose.friend,
      teamInviteTarget => InvitePurpose.team,
      _ => null,
    };
  }

  static InvitePurpose? _purposeFromPath(String path) {
    final p = path.toLowerCase();
    if (p == inviteWebPath || p.startsWith('$inviteWebPath/')) {
      return InvitePurpose.friend;
    }
    if (p == teamInviteWebPath || p.startsWith('$teamInviteWebPath/')) {
      return InvitePurpose.team;
    }
    return null;
  }

  /// Convenience for callers that only need to know "is this any invite".
  static bool matchesInviteUri(Uri uri) => parseInviteUri(uri) != null;

  /// Pure token reader shared by the deep-link handlers and tests.
  static String? readInviteToken(Uri uri) => _extractInviteTokenFromUri(uri);

  static String? _extractInviteTokenFromUri(Uri uri) {
    var token = uri.queryParameters['token']?.trim();
    if (token != null && token.isNotEmpty) {
      return token;
    }

    final fragment = uri.fragment.trim();
    if (fragment.isNotEmpty) {
      try {
        token = Uri.splitQueryString(fragment)['token']?.trim();
        if (token != null && token.isNotEmpty) {
          return token;
        }
      } catch (_) {}
    }

    return null;
  }

  // ---------------------------------------------------------------------------
  // Pending invite persistence (token + purpose only; no personal data)
  // ---------------------------------------------------------------------------

  Future<void> savePendingInvite(PendingInvite invite) async {
    await _storageService.savePendingFriendInviteToken(invite.token);
    await _storageService.savePendingInvitePurpose(invite.purpose.wire);
  }

  Future<PendingInvite?> getPendingInvite() async {
    final token = await _storageService.getPendingFriendInviteToken();
    if (token == null || token.trim().isEmpty) return null;
    final purpose =
        InvitePurposeWire.fromWire(
          await _storageService.getPendingInvitePurpose(),
        ) ??
        InvitePurpose.friend;
    return PendingInvite(token: token.trim(), purpose: purpose);
  }

  Future<void> clearPendingInvite() async {
    await _storageService.clearPendingFriendInviteToken();
  }

  // ---------------------------------------------------------------------------
  // Server calls (Firebase canonical auth only)
  // ---------------------------------------------------------------------------

  /// Read-only. Returns the server's purpose and the inviter's display info
  /// for the confirmation step. Never consumes the token.
  Future<InvitePreview> previewInvite(String rawToken) async {
    try {
      final callable = _functions.httpsCallable('previewInviteToken');
      final result = await callable.call({'token': rawToken});
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final preview = InvitePreview.fromMap(data);
      debugPrint(
        '[FriendInvite] preview status=${preview.status} purpose=${preview.purpose}',
      );
      return preview;
    } on FirebaseFunctionsException catch (e) {
      // Rethrown on purpose: a transport / deployment failure (unavailable,
      // deadline-exceeded, not-found, internal …) is NOT an invalid invite.
      // Only a status the server actually returned may retire the token;
      // the caller keeps it pending otherwise.
      debugPrint('[FriendInvite] preview ${PrivacyLogUtils.errorSummary(e)}');
      rethrow;
    }
  }

  /// User-facing text for a callable failure surfaced by [previewInvite].
  String describeFunctionsError(FirebaseFunctionsException error) =>
      _functionsErrorMessage(error);

  /// Consumes a FRIEND_INVITE token. Call ONLY after the user explicitly
  /// confirmed in the app (see FriendInviteConfirmationSheet).
  Future<FriendInviteAcceptResult> acceptFriendInvite(String rawToken) async {
    try {
      debugPrint('[FriendInvite] acceptFriendInvite start');
      if (!hasCanonicalFirebaseSession) {
        await _authService.ensureCanonicalAppSession();
      }
      if (!hasCanonicalFirebaseSession) {
        return const FriendInviteAcceptResult(
          status: FriendInviteAcceptStatus.pendingLogin,
        );
      }

      final callable = _functions.httpsCallable('acceptFriendInvite');
      final result = await callable.call({'token': rawToken});
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final parsedResult = _acceptResultFromMap(data);
      debugPrint(
        '[FriendInvite] acceptFriendInvite result=${parsedResult.status}',
      );
      return parsedResult;
    } on FirebaseFunctionsException catch (e) {
      debugPrint(
        '[FriendInvite] acceptFriendInvite ${PrivacyLogUtils.errorSummary(e)}',
      );

      if (e.code == 'unauthenticated' || e.code == 'failed-precondition') {
        return FriendInviteAcceptResult(
          status: FriendInviteAcceptStatus.pendingVerification,
          message: _functionsErrorMessage(e),
        );
      }

      return FriendInviteAcceptResult(
        status: FriendInviteAcceptStatus.error,
        message: _functionsErrorMessage(e),
      );
    } catch (e) {
      debugPrint(
        '[FriendInvite] acceptFriendInvite ${PrivacyLogUtils.errorSummary(e)}',
      );
      return FriendInviteAcceptResult(
        status: FriendInviteAcceptStatus.error,
        message: '친구 초대를 처리하지 못했어요: $e',
      );
    }
  }

  /// Turns a TEAM_INVITE token into the canonical pending team invitation.
  /// Membership is still decided in the existing team response screen.
  Future<TeamInviteRedeemResult> redeemTeamShareInvite(String rawToken) async {
    try {
      if (!hasCanonicalFirebaseSession) {
        await _authService.ensureCanonicalAppSession();
      }
      final callable = _functions.httpsCallable('redeemEventTeamShareInvite');
      final result = await callable.call({'token': rawToken});
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final parsed = TeamInviteRedeemResult.fromMap(data);
      debugPrint(
        '[FriendInvite] redeemTeamShareInvite result=${parsed.status}',
      );
      return parsed;
    } on FirebaseFunctionsException catch (e) {
      debugPrint(
        '[FriendInvite] redeemTeamShareInvite ${PrivacyLogUtils.errorSummary(e)}',
      );
      return TeamInviteRedeemResult(
        status: TeamInviteRedeemStatus.error,
        message: _functionsErrorMessage(e),
      );
    } catch (e) {
      return TeamInviteRedeemResult(
        status: TeamInviteRedeemStatus.error,
        message: '팀 초대를 처리하지 못했어요: $e',
      );
    }
  }

  FriendInviteAcceptResult _acceptResultFromMap(Map<String, dynamic> data) {
    final rawStatus = data['status']?.toString() ?? 'invalid';
    final status = switch (rawStatus) {
      'accepted' => FriendInviteAcceptStatus.accepted,
      'already_friends' => FriendInviteAcceptStatus.alreadyFriends,
      'expired' => FriendInviteAcceptStatus.expired,
      'self_invite' => FriendInviteAcceptStatus.selfInvite,
      'blocked' => FriendInviteAcceptStatus.blockedRelationship,
      'pending_login' => FriendInviteAcceptStatus.pendingLogin,
      'pending_verification' => FriendInviteAcceptStatus.pendingVerification,
      'invalid' => FriendInviteAcceptStatus.invalid,
      _ => FriendInviteAcceptStatus.error,
    };

    return FriendInviteAcceptResult(
      status: status,
      pairId: data['pairId']?.toString(),
      otherUserId: data['otherUserId']?.toString(),
      otherUserName: data['otherUserName']?.toString(),
      message: data['message']?.toString(),
    );
  }

  String _functionsErrorMessage(FirebaseFunctionsException error) {
    final message = error.message?.trim();
    if (message != null && message.isNotEmpty) {
      return message;
    }

    switch (error.code) {
      case 'unauthenticated':
        return '학교 이메일 인증을 완료한 계정으로 다시 로그인해주세요.';
      case 'failed-precondition':
        return '초대를 사용하려면 학교 이메일 인증이 완료되어 있어야 해요.';
      case 'permission-denied':
        return '초대를 처리할 권한이 없어요.';
      case 'unavailable':
        return '서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.';
      default:
        return '초대 처리 중 오류가 발생했어요.';
    }
  }

  static String _shareDisplayName(String inviterName) {
    final trimmed = inviterName.trim();
    return trimmed.isEmpty ? '설레연 친구' : trimmed;
  }
}
