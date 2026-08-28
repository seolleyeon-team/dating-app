import 'package:flutter/foundation.dart';
import 'package:kakao_flutter_sdk_talk/kakao_flutter_sdk_talk.dart';

import '../shared/utils/privacy_log_utils.dart';

class KakaoTalkFriendItem {
  final String uuid;
  final int? serviceUserId;
  final String nickname;
  final String thumbnailUrl;
  final bool isFavorite;
  final bool? allowedMessage;

  const KakaoTalkFriendItem({
    required this.uuid,
    required this.serviceUserId,
    required this.nickname,
    required this.thumbnailUrl,
    required this.isFavorite,
    required this.allowedMessage,
  });

  bool get hasUuid => uuid.trim().isNotEmpty;
  bool get canReceiveMessage => allowedMessage != false;

  String get maskedNickname {
    final value = nickname.trim();
    if (value.isEmpty || value == '이름 없는 친구') return '친구';
    if (value.length == 1) return '*';
    return '${value.substring(0, 1)}***';
  }

  String get maskedUuid =>
      hasUuid && uuid.length >= 4 ? '${uuid.substring(0, 4)}...' : '없음';
}

class KakaoTalkFriendLookupResult {
  final int totalCount;
  final int favoriteCount;
  final List<KakaoTalkFriendItem> friends;

  const KakaoTalkFriendLookupResult({
    required this.totalCount,
    required this.favoriteCount,
    required this.friends,
  });
}

class KakaoConsentStatus {
  final int? userId;
  final bool friendsUsing;
  final bool friendsAgreed;
  final bool talkMessageUsing;
  final bool talkMessageAgreed;

  const KakaoConsentStatus({
    required this.userId,
    required this.friendsUsing,
    required this.friendsAgreed,
    required this.talkMessageUsing,
    required this.talkMessageAgreed,
  });

  factory KakaoConsentStatus.fromScopes({
    required int? userId,
    required Iterable<Scope> scopes,
  }) {
    final scopesById = <String, Scope>{
      for (final scope in scopes) scope.id: scope,
    };
    return KakaoConsentStatus(
      userId: userId,
      friendsUsing:
          scopesById[KakaoTalkFriendService.friendsScope]?.using == true,
      friendsAgreed:
          scopesById[KakaoTalkFriendService.friendsScope]?.agreed == true,
      talkMessageUsing:
          scopesById[KakaoTalkFriendService.talkMessageScope]?.using == true,
      talkMessageAgreed:
          scopesById[KakaoTalkFriendService.talkMessageScope]?.agreed == true,
    );
  }
}

class KakaoTalkReviewException implements Exception {
  final String code;
  final String userMessage;

  const KakaoTalkReviewException({
    required this.code,
    required this.userMessage,
  });

  @override
  String toString() => userMessage;
}

class KakaoTalkMessageResult {
  final bool sent;
  final bool receiverUuidExists;
  final int? errorCode;
  final String? errorMessage;

  const KakaoTalkMessageResult({
    required this.sent,
    required this.receiverUuidExists,
    this.errorCode,
    this.errorMessage,
  });
}

class KakaoTalkMemoResult {
  final bool sent;
  final int? errorCode;
  final String? errorMessage;

  const KakaoTalkMemoResult({
    required this.sent,
    this.errorCode,
    this.errorMessage,
  });
}

/// KakaoTalk Social/Friend API와 Message API를 직접 호출하는 서비스입니다.
/// 토큰은 Kakao SDK TokenManager가 관리하며 로그나 화면에 노출하지 않습니다.
class KakaoTalkFriendService {
  static const String friendsScope = 'friends';
  static const String talkMessageScope = 'talk_message';

  static const List<String> _reviewScopes = [friendsScope, talkMessageScope];

  Future<int?> checkLoginUserId() async {
    final tokenInfo = await UserApi.instance.accessTokenInfo();
    return tokenInfo.id;
  }

  Future<User> fetchCurrentUser() async {
    final user = await UserApi.instance.me();
    debugPrint('[KakaoFriend] user me success');
    return user;
  }

  Future<KakaoConsentStatus> getConsentStatus() async {
    final info = await UserApi.instance.scopes(scopes: _reviewScopes);
    return KakaoConsentStatus.fromScopes(
      userId: info.id,
      scopes: info.scopes ?? const <Scope>[],
    );
  }

  /// 필요한 경우에만 추가 동의 화면을 표시하고, 완료 뒤 `me()`를 호출합니다.
  Future<KakaoConsentStatus> ensureRequiredConsents({
    required bool requireTalkMessage,
  }) async {
    try {
      var status = await getConsentStatus();
      final requiredScopes = <String>[
        friendsScope,
        if (requireTalkMessage) talkMessageScope,
      ];

      final unavailableScopes = requiredScopes
          .where((scope) {
            return switch (scope) {
              friendsScope => !status.friendsUsing,
              talkMessageScope => !status.talkMessageUsing,
              _ => true,
            };
          })
          .toList(growable: false);
      if (unavailableScopes.isNotEmpty) {
        throw KakaoTalkReviewException(
          code: 'scope_not_enabled',
          userMessage: '카카오디벨로퍼스에서 친구목록/메시지 동의항목이 사용 설정되지 않았어요. 설정을 확인해 주세요.',
        );
      }

      final missingScopes = requiredScopes
          .where((scope) {
            return switch (scope) {
              friendsScope => !status.friendsAgreed,
              talkMessageScope => !status.talkMessageAgreed,
              _ => false,
            };
          })
          .toList(growable: false);

      if (missingScopes.isNotEmpty) {
        debugPrint(
          '[KakaoFriend] consent requested scopes=${missingScopes.join(',')}',
        );
        await UserApi.instance.loginWithNewScopes(missingScopes);
      }

      // 팀멤버의 앱 연결이 정리되지 않도록 동의 이후 사용자 정보 조회까지 완료합니다.
      await fetchCurrentUser();
      status = await getConsentStatus();
      final stillMissing = requiredScopes.any((scope) {
        return switch (scope) {
          friendsScope => !status.friendsAgreed,
          talkMessageScope => !status.talkMessageAgreed,
          _ => false,
        };
      });
      if (stillMissing) {
        throw const KakaoTalkReviewException(
          code: 'consent_not_completed',
          userMessage: '필수 카카오 동의가 완료되지 않았어요. 동의 화면에서 모두 허용해 주세요.',
        );
      }
      return status;
    } on KakaoTalkReviewException {
      rethrow;
    } on KakaoAuthException catch (error) {
      if (error.error == AuthErrorCause.accessDenied) {
        throw const KakaoTalkReviewException(
          code: 'consent_cancelled',
          userMessage: '카카오 추가 동의가 취소되었어요.',
        );
      }
      throw KakaoTalkReviewException(
        code: error.error.name,
        userMessage: _consentFailureMessage(error),
      );
    } on KakaoClientException catch (error) {
      if (error.reason == ClientErrorCause.cancelled) {
        throw const KakaoTalkReviewException(
          code: 'consent_cancelled',
          userMessage: '카카오 추가 동의가 취소되었어요.',
        );
      }
      throw KakaoTalkReviewException(
        code: error.reason.name,
        userMessage: _consentFailureMessage(error),
      );
    } catch (error) {
      throw KakaoTalkReviewException(
        code: 'consent_failed',
        userMessage: _consentFailureMessage(error),
      );
    }
  }

  /// 실제 Friend API (`TalkApi.friends`)를 호출합니다.
  Future<KakaoTalkFriendLookupResult> fetchFriends({
    bool requestConsentIfNeeded = true,
  }) async {
    if (requestConsentIfNeeded) {
      await ensureRequiredConsents(requireTalkMessage: true);
    }

    try {
      final result = await _fetchFriendsOnce();
      debugPrint(
        '[KakaoFriend] friends fetch success count=${result.friends.length}',
      );
      return result;
    } catch (error) {
      if (!requestConsentIfNeeded || !_looksLikeInsufficientScope(error)) {
        rethrow;
      }

      // 카카오 콘솔에서 동의항목을 사용 설정한 뒤의 첫 호출에도 대응합니다.
      await ensureRequiredConsents(requireTalkMessage: true);
      final result = await _fetchFriendsOnce();
      debugPrint(
        '[KakaoFriend] friends fetch success count=${result.friends.length}',
      );
      return result;
    }
  }

  /// 체크리스트의 첫 Message API 단계인 `나에게 보내기`를 실제 호출합니다.
  Future<KakaoTalkMemoResult> sendTestMessageToMe({Uri? appUrl}) async {
    try {
      await ensureRequiredConsents(requireTalkMessage: true);
      final linkUrl = appUrl ?? Uri.parse('https://seolleyeon-final.web.app');
      final link = Link(webUrl: linkUrl, mobileWebUrl: linkUrl);
      await TalkApi.instance.sendDefaultMemo(
        TextTemplate(
          text: '설레연 카카오 Message API 나에게 보내기 테스트입니다.',
          link: link,
          buttons: [Button(title: '설레연 열기', link: link)],
          buttonTitle: '설레연 열기',
        ),
      );
      debugPrint('[KakaoMessage] memo send success');
      return const KakaoTalkMemoResult(sent: true);
    } catch (error) {
      final code = _kakaoErrorCode(error);
      final detail = _safeErrorMessage(error);
      debugPrint(
        '[KakaoMessage] memo send failed code=${code ?? 'unknown'} '
        'message=${PrivacyLogUtils.errorSummary(error)}',
      );
      return KakaoTalkMemoResult(
        sent: false,
        errorCode: code,
        errorMessage: detail,
      );
    }
  }

  /// 실제 Message API (`TalkApi.sendDefaultMessage`)를 호출합니다.
  /// `inviteUrl`은 기존 설레연 초대 링크를 사용하며 수신 UUID는 로그에 노출하지 않습니다.
  Future<KakaoTalkMessageResult> sendMeetingInviteMessage({
    required String receiverUuid,
    required String inviterName,
    required Uri inviteUrl,
  }) async {
    final hasReceiverUuid = receiverUuid.trim().isNotEmpty;
    if (!hasReceiverUuid) {
      const message = '메시지를 보낼 친구 UUID가 없어요.';
      debugPrint(
        '[KakaoMessage] send failed code=no_receiver_uuid message=$message',
      );
      return const KakaoTalkMessageResult(
        sent: false,
        receiverUuidExists: false,
        errorCode: null,
        errorMessage: message,
      );
    }

    try {
      await ensureRequiredConsents(requireTalkMessage: true);
      final sender = _displayName(inviterName);
      final link = Link(webUrl: inviteUrl, mobileWebUrl: inviteUrl);
      final template = TextTemplate(
        text: '$sender님이 설레연 3:3 미팅 팀에 함께 참여하자고 초대했어요.',
        link: link,
        buttons: [Button(title: '3:3 미팅 참여하기', link: link)],
        buttonTitle: '3:3 미팅 참여하기',
      );
      final result = await TalkApi.instance.sendDefaultMessage(
        receiverUuids: [receiverUuid],
        template: template,
      );
      final sent =
          result.successfulReceiverUuids?.contains(receiverUuid) == true;
      final failures = result.failureInfos;
      final failure = failures != null && failures.isNotEmpty
          ? failures.first
          : null;

      if (sent) {
        debugPrint('[KakaoMessage] send success receiverUuidExists=true');
        return const KakaoTalkMessageResult(
          sent: true,
          receiverUuidExists: true,
        );
      }

      final code = failure?.code;
      final message = failure?.msg ?? '카카오톡 메시지 발송 결과를 확인하지 못했어요.';
      debugPrint(
        '[KakaoMessage] send failed code=${code ?? 'unknown'} message=$message',
      );
      return KakaoTalkMessageResult(
        sent: false,
        receiverUuidExists: true,
        errorCode: code,
        errorMessage: message,
      );
    } catch (error) {
      final code = _kakaoErrorCode(error);
      final detail = _safeErrorMessage(error);
      debugPrint(
        '[KakaoMessage] send failed code=${code ?? 'unknown'} '
        'message=${PrivacyLogUtils.errorSummary(error)}',
      );
      return KakaoTalkMessageResult(
        sent: false,
        receiverUuidExists: true,
        errorCode: code,
        errorMessage: detail,
      );
    }
  }

  Future<KakaoTalkFriendLookupResult> _fetchFriendsOnce() async {
    var page = await TalkApi.instance.friends(limit: 100);
    var totalCount = page.totalCount;
    var favoriteCount = page.favoriteCount ?? 0;
    final fetchedFriends = <Friend>[];
    final fetchedUuids = <String>{};
    final visitedNextUrls = <String>{};

    while (true) {
      final elements = page.elements ?? const <Friend>[];
      for (final friend in elements) {
        if (fetchedUuids.add(friend.uuid)) fetchedFriends.add(friend);
      }

      final afterUrl = page.afterUrl;
      if (afterUrl == null || afterUrl.isEmpty) break;
      if (!visitedNextUrls.add(afterUrl)) break;

      page = await TalkApi.instance.friends(
        context: FriendsContext.fromUrl(Uri.parse(afterUrl)),
      );
      totalCount = page.totalCount;
      favoriteCount = page.favoriteCount ?? favoriteCount;
    }

    return KakaoTalkFriendLookupResult(
      totalCount: totalCount,
      favoriteCount: favoriteCount,
      friends: fetchedFriends
          .map(
            (friend) => KakaoTalkFriendItem(
              uuid: friend.uuid,
              serviceUserId: friend.id,
              nickname: friend.profileNickname?.trim().isNotEmpty == true
                  ? friend.profileNickname!.trim()
                  : '이름 없는 친구',
              thumbnailUrl: friend.profileThumbnailImage?.trim() ?? '',
              isFavorite: friend.favorite == true,
              allowedMessage: friend.allowedMsg,
            ),
          )
          .toList(growable: false),
    );
  }

  bool _looksLikeInsufficientScope(Object error) {
    final text = error.toString().toLowerCase();
    return text.contains('insufficient scopes') ||
        text.contains('required_scopes') ||
        text.contains('-402');
  }

  String _displayName(String value) {
    final trimmed = value.trim();
    return trimmed.isEmpty ? '친구' : trimmed;
  }

  int? _kakaoErrorCode(Object error) {
    if (error is KakaoApiException) {
      final code = error.toJson()['code'];
      return code is int ? code : int.tryParse('$code');
    }
    return null;
  }

  String _consentFailureMessage(Object error) {
    if (error is KakaoAuthException) {
      if (error.error == AuthErrorCause.unauthorized) {
        return '카카오 앱에 친구목록/메시지 사용 권한이 없어요. 카카오디벨로퍼스 설정을 확인해 주세요.';
      }
      if (error.error == AuthErrorCause.invalidScope) {
        return '카카오 친구목록/메시지 동의항목 설정이 올바르지 않아요.';
      }
    }
    if (error is KakaoClientException &&
        error.reason == ClientErrorCause.tokenNotFound) {
      return '카카오 로그인 정보가 없어요. 카카오로 다시 로그인해 주세요.';
    }
    if (error is KakaoApiException) {
      if (error.code == ApiErrorCause.unsupportedApi) {
        return '카카오 앱에서 Friend/Message API 사용 설정을 완료하지 않았어요.';
      }
      if (error.code == ApiErrorCause.insufficientScope) {
        return '카카오 친구목록/메시지 동의가 필요해요.';
      }
      if (error.code == ApiErrorCause.invalidToken) {
        return '카카오 로그인 세션이 만료되었어요. 다시 로그인해 주세요.';
      }
      if (error.code == ApiErrorCause.notTalkUser) {
        return '카카오톡을 사용 중인 계정으로 로그인해 주세요.';
      }
    }
    return '카카오 추가 동의를 완료하지 못했어요. 다시 시도해 주세요.';
  }

  String _safeErrorMessage(Object error) {
    final message = switch (error) {
      KakaoApiException() => error.msg,
      KakaoAuthException() => error.errorDescription ?? error.error.name,
      KakaoClientException() => error.msg,
      KakaoTalkReviewException() => error.userMessage,
      _ => error.toString().replaceFirst('Exception: ', ''),
    };
    return message
        .replaceAll(
          RegExp(r'access[_ -]?token[^, ]*', caseSensitive: false),
          '[redacted]',
        )
        .replaceAll(
          RegExp(r'refresh[_ -]?token[^, ]*', caseSensitive: false),
          '[redacted]',
        );
  }
}
