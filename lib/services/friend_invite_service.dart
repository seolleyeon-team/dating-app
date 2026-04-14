import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart'
    show
        TargetPlatform,
        debugPrint,
        debugPrintStack,
        defaultTargetPlatform,
        kIsWeb;
import 'package:flutter/services.dart';
import 'package:kakao_flutter_sdk_share/kakao_flutter_sdk_share.dart';
import 'package:url_launcher/url_launcher.dart';

import 'auth_service.dart';
import 'storage_service.dart';

enum FriendInviteAcceptStatus {
  accepted,
  alreadyFriends,
  expired,
  invalid,
  selfInvite,
  pendingLogin,
  pendingVerification,
  error,
}

enum FriendInviteShareSurface {
  kakaoTalkApp,
  webSharePage,
  desktopSharePage,
}

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
        return '\uCE74\uCE74\uC624\uD1A1 \uACF5\uC720 \uD654\uBA74\uC744 \uC5F4\uC5C8\uC5B4\uC694.';
      case FriendInviteShareSurface.webSharePage:
        return '\uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uC5C8\uC5B4\uC694.';
      case FriendInviteShareSurface.desktopSharePage:
        return inviteLinkCopied
            ? '\uB370\uC2A4\uD06C\uD1B1\uC5D0\uC11C \uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uACE0 \uCD08\uB300 \uB9C1\uD06C\uB97C \uBCF5\uC0AC\uD588\uC5B4\uC694.'
            : '\uB370\uC2A4\uD06C\uD1B1\uC5D0\uC11C \uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uC5C8\uC5B4\uC694.';
    }
  }
}

class FriendInviteSharePayload {
  final String inviteId;
  final String inviteToken;
  final String inviteUrl;
  final String deepLinkPath;
  final DateTime? expiresAt;

  const FriendInviteSharePayload({
    required this.inviteId,
    required this.inviteToken,
    required this.inviteUrl,
    required this.deepLinkPath,
    required this.expiresAt,
  });

  factory FriendInviteSharePayload.fromMap(Map<String, dynamic> data) {
    return FriendInviteSharePayload(
      inviteId: data['inviteId']?.toString() ?? '',
      inviteToken: data['inviteToken']?.toString() ?? '',
      inviteUrl: data['inviteUrl']?.toString() ?? '',
      deepLinkPath: data['deepLinkPath']?.toString() ?? '/invite/friend',
      expiresAt: DateTime.tryParse(data['expiresAt']?.toString() ?? ''),
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
            ? '$name\uACFC \uCE5C\uAD6C\uAC00 \uB418\uC5C8\uC5B4\uC694.'
            : '\uCE5C\uAD6C\uAC00 \uCD94\uAC00\uB418\uC5C8\uC5B4\uC694.';
      case FriendInviteAcceptStatus.alreadyFriends:
        final name = otherUserName?.trim();
        return (name != null && name.isNotEmpty)
            ? '$name\uB2D8\uACFC \uC774\uBBF8 \uCE5C\uAD6C\uC608\uC694.'
            : '\uC774\uBBF8 \uCE5C\uAD6C\uB85C \uC5F0\uACB0\uB418\uC5B4 \uC788\uC5B4\uC694.';
      case FriendInviteAcceptStatus.expired:
        return '\uCE5C\uAD6C \uCD08\uB300 \uB9C1\uD06C\uAC00 \uB9CC\uB8CC\uB418\uC5C8\uC5B4\uC694.';
      case FriendInviteAcceptStatus.invalid:
        return '\uC720\uD6A8\uD558\uC9C0 \uC54A\uC740 \uCE5C\uAD6C \uCD08\uB300 \uB9C1\uD06C\uC608\uC694.';
      case FriendInviteAcceptStatus.selfInvite:
        return '\uB0B4\uAC00 \uB9CC\uB4E0 \uCD08\uB300 \uB9C1\uD06C\uB85C\uB294 \uCE5C\uAD6C\uB97C \uCD94\uAC00\uD560 \uC218 \uC5C6\uC5B4\uC694.';
      case FriendInviteAcceptStatus.pendingLogin:
        return '\uB85C\uADF8\uC778\uD558\uBA74 \uC790\uB3D9\uC73C\uB85C \uCE5C\uAD6C \uCD94\uAC00\uB97C \uC774\uC5B4\uC11C \uC9C4\uD589\uD560\uAC8C\uC694.';
      case FriendInviteAcceptStatus.pendingVerification:
        return '\uD559\uAD50 \uC774\uBA54\uC77C \uC778\uC99D\uC744 \uB9C8\uCE58\uBA74 \uC790\uB3D9\uC73C\uB85C \uCE5C\uAD6C \uCD94\uAC00\uB97C \uC774\uC5B4\uC11C \uC9C4\uD589\uD560\uAC8C\uC694.';
      case FriendInviteAcceptStatus.error:
        return '\uCE5C\uAD6C \uCD08\uB300\uB97C \uCC98\uB9AC\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC2DC\uB3C4\uD574\uC8FC\uC138\uC694.';
    }
  }
}

class FriendInviteService {
  FriendInviteService({
    FirebaseFunctions? functions,
    StorageService? storageService,
    AuthService? authService,
  })  : _functions =
            functions ?? FirebaseFunctions.instanceFor(region: _functionsRegion),
        _storageService = storageService ?? StorageService(),
        _authService = authService ?? AuthService();

  static const String _functionsRegion = 'asia-northeast3';
  static const String inviteWebHost = 'seolleyeon.web.app';
  static const String inviteWebPath = '/invite/friend';
  static const String inviteScheme = 'seolleyeon';
  static const String inviteTarget = 'friend_invite';

  final FirebaseFunctions _functions;
  final StorageService _storageService;
  final AuthService _authService;

  bool get _isDesktopPlatform =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.windows ||
          defaultTargetPlatform == TargetPlatform.macOS ||
          defaultTargetPlatform == TargetPlatform.linux);

  Future<FriendInviteSharePayload> createFriendInvite() async {
    try {
      debugPrint('[FriendInvite] createFriendInvite start');
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('\uB85C\uADF8\uC778\uC774 \uD544\uC694\uD574\uC694.');
      }

      final hasFirebaseSession =
          await _authService.ensureFirebaseSessionForVerifiedUser(kakaoUserId);

      final kakaoAccessToken = FirebaseAuth.instance.currentUser == null
          ? await _authService.getKakaoAccessTokenForFunctions()
          : null;

      final Map<String, dynamic> callData = {'shareChannel': 'kakaotalk'};
      if (kakaoAccessToken != null && kakaoAccessToken.isNotEmpty) {
        callData['kakaoAccessToken'] = kakaoAccessToken;
      }

      debugPrint(
        '[FriendInvite] createFriendInvite auth firebaseAttached=$hasFirebaseSession firebaseUid=${FirebaseAuth.instance.currentUser?.uid} hasKakaoAccessToken=${kakaoAccessToken != null && kakaoAccessToken.isNotEmpty}',
      );

      if (FirebaseAuth.instance.currentUser == null &&
          (kakaoAccessToken == null || kakaoAccessToken.isEmpty)) {
        if (kIsWeb) {
          throw Exception(
            '\uCE74\uCE74\uC624 \uB85C\uADF8\uC778\uC774 \uB9CC\uB8CC\uB418\uC5C8\uC5B4\uC694. \uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C \uB2E4\uC2DC \uB85C\uADF8\uC778\uD55C \uB4A4 \uC5F0\uC138 \uBA54\uC77C \uC778\uC99D\uAE4C\uC9C0 \uC644\uB8CC\uD55C \uB2E4\uC74C \uCE5C\uAD6C \uCD08\uB300\uB97C \uC2DC\uB3C4\uD574\uC8FC\uC138\uC694.',
          );
        }

        throw Exception(
          '\uB85C\uADF8\uC778\uC774 \uD544\uC694\uD574\uC694. \uCE74\uCE74\uC624 \uB85C\uADF8\uC778 \uD6C4 \uC5F0\uC138 \uC774\uBA54\uC77C \uC778\uC99D\uC744 \uC644\uB8CC\uD574\uC8FC\uC138\uC694.',
        );
      }

      final callable = _functions.httpsCallable('createFriendInvite');
      final result = await callable.call(callData);
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final payload = FriendInviteSharePayload.fromMap(data);

      if (payload.inviteId.isEmpty ||
          payload.inviteToken.isEmpty ||
          payload.inviteUrl.isEmpty) {
        throw Exception(
          '\uCE5C\uAD6C \uCD08\uB300 \uC751\uB2F5\uC774 \uC62C\uBC14\uB974\uC9C0 \uC54A\uC544\uC694.',
        );
      }

      debugPrint(
        '[FriendInvite] createFriendInvite success inviteId=${payload.inviteId} inviteUrl=${payload.inviteUrl}',
      );
      return payload;
    } on FirebaseFunctionsException catch (e, st) {
      debugPrint(
        '[FriendInvite] createFriendInvite functions error code=${e.code} message=${e.message}',
      );
      debugPrintStack(stackTrace: st);
      throw Exception(_functionsErrorMessage(e));
    } catch (e, st) {
      debugPrint('[FriendInvite] createFriendInvite error: $e');
      debugPrintStack(stackTrace: st);
      throw Exception(
        '\uCE5C\uAD6C \uCD08\uB300 \uB9C1\uD06C\uB97C \uB9CC\uB4E4\uC9C0 \uBABB\uD588\uC5B4\uC694: $e',
      );
    }
  }

  Future<FriendInviteShareResult> shareInviteViaKakao({
    required FriendInviteSharePayload payload,
    required String inviterName,
  }) async {
    final inviteUri = Uri.parse(payload.inviteUrl);
    debugPrint('[FriendInvite] share target url=$inviteUri');

    final link = Link(
      webUrl: inviteUri,
      mobileWebUrl: inviteUri,
    );

    final template = TextTemplate(
      text:
          '\uC124\uB808\uC5F0\uC5D0\uC11C \uCE5C\uAD6C \uCD94\uAC00\uD558\uAE30\n${_shareDisplayName(inviterName)}\uB2D8\uC774 \uCE5C\uAD6C\uB85C \uCD08\uB300\uD588\uC5B4\uC694.',
      link: link,
      buttons: [
        Button(
          title: '\uCE5C\uAD6C \uCD94\uAC00\uD558\uAE30',
          link: link,
        ),
      ],
      buttonTitle: '\uCE5C\uAD6C \uCD94\uAC00\uD558\uAE30',
    );

    try {
      debugPrint(
        "[FriendInvite] shareInviteViaKakao start platform=${kIsWeb ? 'web' : 'native'} inviteUrl=${payload.inviteUrl}",
      );

      if (kIsWeb) {
        final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
          template: template,
        );
        debugPrint('[FriendInvite] web sharer uri=$sharerUri');

        final launched = await launchUrl(
          sharerUri,
          webOnlyWindowName: '_self',
        );
        if (!launched) {
          throw Exception(
            '\uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uC9C0 \uBABB\uD588\uC5B4\uC694.',
          );
        }

        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.webSharePage,
        );
      }

      if (_isDesktopPlatform) {
        final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
          template: template,
        );
        debugPrint('[FriendInvite] desktop sharer uri=$sharerUri');

        await Clipboard.setData(ClipboardData(text: payload.inviteUrl));
        final launched = await launchUrl(
          sharerUri,
          mode: LaunchMode.externalApplication,
        );
        if (!launched) {
          throw Exception(
            '\uB370\uC2A4\uD06C\uD1B1\uC5D0\uC11C \uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uC9C0 \uBABB\uD588\uC5B4\uC694.',
          );
        }

        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.desktopSharePage,
          inviteLinkCopied: true,
        );
      }

      final canShareToTalk =
          await ShareClient.instance.isKakaoTalkSharingAvailable();
      debugPrint('[FriendInvite] KakaoTalk available=$canShareToTalk');

      if (canShareToTalk) {
        final sharingUri = await ShareClient.instance.shareDefault(
          template: template,
        );
        debugPrint('[FriendInvite] launchKakaoTalk uri=$sharingUri');
        await ShareClient.instance.launchKakaoTalk(sharingUri);

        return const FriendInviteShareResult(
          surface: FriendInviteShareSurface.kakaoTalkApp,
        );
      }

      final sharerUri = await WebSharerClient.instance.makeDefaultUrl(
        template: template,
      );
      debugPrint('[FriendInvite] native fallback sharer uri=$sharerUri');

      final launched = await launchUrl(
        sharerUri,
        mode: LaunchMode.externalApplication,
      );
      if (!launched) {
        throw Exception(
          '\uCE74\uCE74\uC624 \uACF5\uC720 \uD398\uC774\uC9C0\uB97C \uC5F4\uC9C0 \uBABB\uD588\uC5B4\uC694.',
        );
      }

      return const FriendInviteShareResult(
        surface: FriendInviteShareSurface.webSharePage,
      );
    } catch (e, st) {
      debugPrint('[FriendInvite] shareInviteViaKakao error: $e');
      debugPrintStack(stackTrace: st);
      throw Exception(
        '\uCE74\uCE74\uC624\uD1A1 \uACF5\uC720\uB97C \uC2E4\uD589\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694: $e',
      );
    }
  }

  bool isFriendInviteUri(Uri uri) {
    final token = extractInviteToken(uri);
    if (token == null || token.isEmpty) {
      return false;
    }

    final normalizedPath = uri.path.toLowerCase();
    final normalizedHost = uri.host.toLowerCase();

    if (uri.queryParameters['target'] == inviteTarget) {
      return true;
    }

    if (normalizedHost == 'kakaolink' &&
        uri.scheme.toLowerCase().startsWith('kakao')) {
      return true;
    }

    if (uri.scheme == inviteScheme) {
      if (normalizedHost == 'invite' && normalizedPath == '/friend') {
        return true;
      }
      return normalizedPath == inviteWebPath;
    }

    final isWebLink =
        (uri.scheme == 'https' || uri.scheme == 'http') &&
        normalizedHost == inviteWebHost;
    if (!isWebLink) {
      return false;
    }

    return normalizedPath == inviteWebPath ||
        normalizedPath.startsWith('$inviteWebPath/');
  }

  String? extractInviteToken(Uri uri) {
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

  Future<void> savePendingInviteToken(String token) async {
    await _storageService.savePendingFriendInviteToken(token);
  }

  Future<String?> getPendingInviteToken() async {
    return _storageService.getPendingFriendInviteToken();
  }

  Future<void> clearPendingInviteToken() async {
    await _storageService.clearPendingFriendInviteToken();
  }

  Future<FriendInviteAcceptResult?> processPendingInviteIfPossible() async {
    final token = await getPendingInviteToken();
    debugPrint(
      '[FriendInvite] processPendingInviteIfPossible tokenExists=${token != null && token.trim().isNotEmpty}',
    );

    if (token == null || token.trim().isEmpty) {
      return null;
    }

    final kakaoUserId = await _storageService.getKakaoUserId();
    debugPrint(
      '[FriendInvite] processPendingInviteIfPossible kakaoUserId=$kakaoUserId',
    );

    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      return const FriendInviteAcceptResult(
        status: FriendInviteAcceptStatus.pendingLogin,
      );
    }

    await _authService.ensureFirebaseSessionForVerifiedUser(kakaoUserId);

    final result = await acceptFriendInvite(token);
    debugPrint(
      '[FriendInvite] processPendingInviteIfPossible result=${result.status}',
    );

    if (result.isTerminal) {
      await clearPendingInviteToken();
    }

    return result;
  }

  Future<FriendInviteAcceptResult> acceptFriendInvite(String rawToken) async {
    try {
      debugPrint('[FriendInvite] acceptFriendInvite start');

      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
        await _authService.ensureFirebaseSessionForVerifiedUser(kakaoUserId);
      }

      final kakaoAccessToken = FirebaseAuth.instance.currentUser == null
          ? await _authService.getKakaoAccessTokenForFunctions()
          : null;

      final Map<String, dynamic> callData = {'token': rawToken};
      if (kakaoAccessToken != null && kakaoAccessToken.isNotEmpty) {
        callData['kakaoAccessToken'] = kakaoAccessToken;
      }

      debugPrint(
        '[FriendInvite] acceptFriendInvite auth firebaseUid=${FirebaseAuth.instance.currentUser?.uid} hasKakaoAccessToken=${kakaoAccessToken != null && kakaoAccessToken.isNotEmpty}',
      );

      if (FirebaseAuth.instance.currentUser == null &&
          (kakaoAccessToken == null || kakaoAccessToken.isEmpty)) {
        return const FriendInviteAcceptResult(
          status: FriendInviteAcceptStatus.pendingVerification,
          message: '\uCE74\uCE74\uC624 \uB85C\uADF8\uC778\uC774 \uD544\uC694\uD574\uC694.',
        );
      }

      final callable = _functions.httpsCallable('acceptFriendInvite');
      final result = await callable.call(callData);
      final data = Map<String, dynamic>.from(
        (result.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      debugPrint('[FriendInvite] acceptFriendInvite result=$data');
      return _acceptResultFromMap(data);
    } on FirebaseFunctionsException catch (e, st) {
      debugPrint(
        '[FriendInvite] acceptFriendInvite functions error code=${e.code} message=${e.message}',
      );
      debugPrintStack(stackTrace: st);

      if (e.code == 'unauthenticated') {
        return const FriendInviteAcceptResult(
          status: FriendInviteAcceptStatus.pendingVerification,
        );
      }

      return FriendInviteAcceptResult(
        status: FriendInviteAcceptStatus.error,
        message: _functionsErrorMessage(e),
      );
    } catch (e, st) {
      debugPrint('[FriendInvite] acceptFriendInvite error: $e');
      debugPrintStack(stackTrace: st);
      return FriendInviteAcceptResult(
        status: FriendInviteAcceptStatus.error,
        message:
            '\uCE5C\uAD6C \uCD08\uB300\uB97C \uCC98\uB9AC\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694: $e',
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
        return '\uD559\uAD50 \uC774\uBA54\uC77C \uC778\uC99D\uC744 \uC644\uB8CC\uD55C \uACC4\uC815\uC73C\uB85C \uB2E4\uC2DC \uB85C\uADF8\uC778\uD574\uC8FC\uC138\uC694.';
      case 'failed-precondition':
        return '\uCE5C\uAD6C \uCD08\uB300\uB97C \uC0AC\uC6A9\uD558\uB824\uBA74 \uD559\uAD50 \uC774\uBA54\uC77C \uC778\uC99D\uC774 \uC644\uB8CC\uB418\uC5B4 \uC788\uC5B4\uC57C \uD574\uC694.';
      case 'permission-denied':
        return '\uCE5C\uAD6C \uCD08\uB300\uB97C \uCC98\uB9AC\uD560 \uAD8C\uD55C\uC774 \uC5C6\uC5B4\uC694.';
      case 'unavailable':
        return '\uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC2DC\uB3C4\uD574\uC8FC\uC138\uC694.';
      default:
        return '\uCE5C\uAD6C \uCD08\uB300 \uCC98\uB9AC \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC5B4\uC694.';
    }
  }

  String _shareDisplayName(String inviterName) {
    final trimmed = inviterName.trim();
    return trimmed.isEmpty ? '\uC124\uB808\uC5F0 \uCE5C\uAD6C' : trimmed;
  }
}
