import 'package:flutter/foundation.dart';

import 'friend_invite_service.dart';

/// 마이페이지·팀 구성 등에서 동일한 카카오 친구 초대(링크 생성 + 공유) 흐름을 쓰기 위한 헬퍼.
class KakaoFriendInviteHelper {
  KakaoFriendInviteHelper._();

  static final FriendInviteService _service = FriendInviteService();

  /// 친구 초대 링크를 만들고 카카오로 공유한다. (FriendInviteService 경로 단일화)
  static Future<FriendInviteShareResult> createAndShareKakaoInvite({
    required String inviterDisplayName,
  }) async {
    debugPrint('[KakaoFriendInvite] createAndShareKakaoInvite');
    final payload = await _service.createFriendInvite();
    return await _service.shareInviteViaKakao(
      payload: payload,
      inviterName: inviterDisplayName,
    );
  }
}
