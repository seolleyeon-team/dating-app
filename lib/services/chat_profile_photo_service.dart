import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';

class ChatProfilePhotoResult {
  final String displayMode;
  final String imageUrl;
  final String approvedAvatarUrl;
  final DateTime? expiresAt;
  final String reason;

  const ChatProfilePhotoResult({
    required this.displayMode,
    required this.imageUrl,
    required this.approvedAvatarUrl,
    this.expiresAt,
    this.reason = '',
  });

  bool get isRealPhoto => displayMode == 'real_photo' && imageUrl.isNotEmpty;

  bool get isExpired {
    final expiry = expiresAt;
    if (expiry == null) return false;
    return DateTime.now().isAfter(expiry.subtract(const Duration(seconds: 20)));
  }

  factory ChatProfilePhotoResult.avatar({
    String approvedAvatarUrl = '',
    String reason = 'fallback',
  }) {
    return ChatProfilePhotoResult(
      displayMode: 'avatar',
      imageUrl: approvedAvatarUrl,
      approvedAvatarUrl: approvedAvatarUrl,
      reason: reason,
    );
  }

  factory ChatProfilePhotoResult.fromMap(
    Map<String, dynamic> data, {
    String fallbackAvatarUrl = '',
  }) {
    final displayMode = data['displayMode']?.toString() ?? 'avatar';
    final approvedAvatarUrl =
        data['approvedAvatarUrl']?.toString() ?? fallbackAvatarUrl;
    final rawImageUrl = data['imageUrl']?.toString() ?? '';
    final expiresAtRaw = data['expiresAt']?.toString();
    return ChatProfilePhotoResult(
      displayMode: displayMode == 'real_photo' ? 'real_photo' : 'avatar',
      imageUrl: rawImageUrl.isNotEmpty ? rawImageUrl : approvedAvatarUrl,
      approvedAvatarUrl: approvedAvatarUrl,
      expiresAt: expiresAtRaw == null || expiresAtRaw.isEmpty
          ? null
          : DateTime.tryParse(expiresAtRaw),
      reason: data['reason']?.toString() ?? '',
    );
  }
}

class ChatProfilePhotoService {
  ChatProfilePhotoService({FirebaseFunctions? functions, FirebaseAuth? auth})
    : _functions =
          functions ?? FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
      _auth = auth ?? FirebaseAuth.instance;

  final FirebaseFunctions _functions;
  final FirebaseAuth _auth;
  final Map<String, ChatProfilePhotoResult> _cache = {};

  Future<ChatProfilePhotoResult> getChatProfilePhoto({
    required String chatRoomId,
    required String targetUid,
    String fallbackAvatarUrl = '',
  }) async {
    if (chatRoomId.trim().isEmpty || targetUid.trim().isEmpty) {
      return ChatProfilePhotoResult.avatar(
        approvedAvatarUrl: fallbackAvatarUrl,
        reason: 'missing_chat_context',
      );
    }

    final cacheKey = '${chatRoomId.trim()}:${targetUid.trim()}';
    final cached = _cache[cacheKey];
    if (cached != null && !cached.isExpired) {
      return cached;
    }

    final currentUser = _auth.currentUser;
    if (currentUser == null) {
      return ChatProfilePhotoResult.avatar(
        approvedAvatarUrl: fallbackAvatarUrl,
        reason: 'not_authenticated',
      );
    }

    try {
      await currentUser.getIdToken(false);
      final callable = _functions.httpsCallable('getChatRealProfilePhoto');
      final response = await callable.call(<String, dynamic>{
        'chatRoomId': chatRoomId,
        'targetUid': targetUid,
      });
      final raw = response.data;
      final data = raw is Map
          ? raw.map((key, value) => MapEntry(key.toString(), value))
          : <String, dynamic>{};
      final result = ChatProfilePhotoResult.fromMap(
        data,
        fallbackAvatarUrl: fallbackAvatarUrl,
      );
      if (result.isRealPhoto) {
        _cache[cacheKey] = result;
      }
      return result;
    } catch (_) {
      return ChatProfilePhotoResult.avatar(
        approvedAvatarUrl: fallbackAvatarUrl,
        reason: 'backend_unavailable',
      );
    }
  }
}
