import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart' show debugPrint, debugPrintStack, kIsWeb;
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
            ? '$name님과 친구가 되었어요.'
            : '친구가 추가되었어요.';
      case FriendInviteAcceptStatus.alreadyFriends:
        final name = otherUserName?.trim();
        return (name != null && name.isNotEmpty)
            ? '$name님은 이미 친구예요.'
            : '이미 친구로 연결되어 있어요.';
      case FriendInviteAcceptStatus.expired:
        return '친구 초대 링크가 만료되었어요.';
      case FriendInviteAcceptStatus.invalid:
        return '유효하지 않은 친구 초대 링크예요.';
      case FriendInviteAcceptStatus.selfInvite:
        return '내가 만든 초대 링크로는 친구를 추가할 수 없어요.';
      case FriendInviteAcceptStatus.pendingLogin:
        return '로그인 후 자동으로 친구 추가를 이어서 진행할게요.';
      case FriendInviteAcceptStatus.pendingVerification:
        return '학교 이메일 인증이 끝나면 자동으로 친구 추가를 이어서 진행할게요.';
      case FriendInviteAcceptStatus.error:
        return '친구 초대를 처리하지 못했어요. 잠시 후 다시 시도해주세요.';
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

  Future<FriendInviteSharePayload> createFriendInvite() async {
    try {
      debugPrint('[FriendInvite] createFriendInvite start');
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인이 필요해요.');
      }

      var hasFirebaseSession = FirebaseAuth.instance.currentUser != null;
      if (!hasFirebaseSession) {
        hasFirebaseSession =
            await _authService.ensureFirebaseSessionForVerifiedUser(kakaoUserId);
      }
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
      if (FirebaseAuth.instance.currentUser == null) {
        if (kakaoAccessToken == null || kakaoAccessToken.isEmpty) {
          if (kIsWeb) {
            throw Exception(
              '카카오 로그인이 만료됐어요. 브라우저에서 다시 로그인한 뒤, '
              '연세 메일 인증까지 완료한 다음 친구 초대를 시도해 주세요.',
            );
          }
          throw Exception(
            '로그인이 필요해요. 카카오 로그인 후 연세 이메일 인증을 완료해주세요.',
          );
        }
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
        throw Exception('친구 초대 응답이 올바르지 않아요.');
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
      throw Exception('친구 초대 링크를 만들지 못했어요: $e');
    }
  }

  Future<void> shareInviteViaKakao({
    required FriendInviteSharePayload payload,
    required String inviterName,
  }) async {
    final inviteUri = Uri.parse(payload.inviteUrl);
    // Android: 버튼 탭 시 웹 URL + 앱 실행 파라미터(카카오링크) 병행 — 스킴 오타 시 웹도 안 열리는 사례 있음
    final executionParams = <String, String>{
      'target': inviteTarget,
      'token': payload.inviteToken,
    };
    debugPrint('[FriendInvite] executionParams=$executionParams');
    final link = Link(
      webUrl: inviteUri,
      mobileWebUrl: inviteUri,
      androidExecutionParams: executionParams,
      iosExecutionParams: executionParams,
    );
    final template = TextTemplate(
      text: '설레연에서 친구 추가하기\n${_shareDisplayName(inviterName)}님이 친구로 초대했어요',
      link: link,
      buttons: [
        Button(
          title: '친구 추가하기',
          link: link,
        ),
      ],
      buttonTitle: '친구 추가하기',
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

        // Web popup blockers can block async new-window opens.
        // Navigating the current tab is the most reliable fallback here.
        final launched = await launchUrl(
          sharerUri,
          webOnlyWindowName: '_self',
        );
        if (!launched) {
          throw Exception('카카오 공유 페이지를 열지 못했어요.');
        }
        return;
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
        return;
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
        throw Exception('카카오 공유 페이지를 열지 못했어요.');
      }
    } catch (e, st) {
      debugPrint('[FriendInvite] shareInviteViaKakao error: $e');
      debugPrintStack(stackTrace: st);
      throw Exception('카카오톡 공유를 실행하지 못했어요: $e');
    }
  }

  bool isFriendInviteUri(Uri uri) {
    final token = extractInviteToken(uri);
    if (token == null || token.isEmpty) return false;

    final normalizedPath = uri.path.toLowerCase();
    final normalizedHost = uri.host.toLowerCase();
    if (uri.queryParameters['target'] == inviteTarget) {
      return true;
    }

    // 카카오톡 공유 버튼 → 앱 실행 시 흔한 형태:
    // kakao{NATIVE_APP_KEY}://kakaolink?target=friend_invite&token=...
    // 일부 기기/버전에서는 target만 빠지거나 순서가 달라질 수 있어 host로 판별한다.
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
    if (!isWebLink) return false;

    return normalizedPath == inviteWebPath ||
        normalizedPath.startsWith('$inviteWebPath/');
  }

  String? extractInviteToken(Uri uri) {
    var token = uri.queryParameters['token']?.trim();
    if (token != null && token.isNotEmpty) return token;

    final frag = uri.fragment.trim();
    if (frag.isNotEmpty) {
      try {
        token = Uri.splitQueryString(frag)['token']?.trim();
        if (token != null && token.isNotEmpty) return token;
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

    // 카카오 커스텀 토큰 세션(UID=카카오ID)을 우선 시도. 실패해도 연세 이메일 링크만으로
    // 로그인된 경우 서버(resolveAuthedAppUser)가 studentEmail로 사용자를 찾을 수 있음.
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
      if (FirebaseAuth.instance.currentUser == null) {
        final kakaoUserId = await _storageService.getKakaoUserId();
        if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
          await _authService.ensureFirebaseSessionForVerifiedUser(kakaoUserId);
        }
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
      if (FirebaseAuth.instance.currentUser == null) {
        if (kakaoAccessToken == null || kakaoAccessToken.isEmpty) {
          return const FriendInviteAcceptResult(
            status: FriendInviteAcceptStatus.pendingVerification,
            message: '카카오 로그인이 필요해요.',
          );
        }
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
        message: '친구 초대를 처리하지 못했어요: $e',
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
        return '학교 이메일 인증이 완료된 계정으로 다시 로그인해주세요.';
      case 'failed-precondition':
        return '친구 초대를 사용하려면 학교 이메일 인증이 완료되어 있어야 해요.';
      case 'permission-denied':
        return '친구 초대를 처리할 권한이 없어요.';
      case 'unavailable':
        return '서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.';
      default:
        return '친구 초대 처리 중 오류가 발생했어요.';
    }
  }

  String _shareDisplayName(String inviterName) {
    final trimmed = inviterName.trim();
    return trimmed.isEmpty ? '설레연 친구' : trimmed;
  }
}
