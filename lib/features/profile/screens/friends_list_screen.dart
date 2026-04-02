import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/friend_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../matching/models/profile_card_args.dart';

class _AppColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color background = Color(0xFFF8F8FA);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF8B8B94);
  static const Color line = Color(0xFFE9E9EE);
  static const Color empty = Color(0xFFB7B7C2);
}

class FriendsListScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onMessage;
  final Function(int)? onTabChanged;

  const FriendsListScreen({
    super.key,
    this.onBack,
    this.onMessage,
    this.onTabChanged,
  });

  @override
  State<FriendsListScreen> createState() => _FriendsListScreenState();
}

class _FriendsListScreenState extends State<FriendsListScreen> {
  final AuthService _authService = AuthService();
  final StorageService _storageService = StorageService();
  final FriendService _friendService = FriendService();
  final UserService _userService = UserService();

  String? _currentUserId;
  bool _isAuthReady = false;
  bool _canReadFriends = false;
  int _friendCountHint = 0;

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final userId = await _storageService.getKakaoUserId();
    if (!mounted) return;

    var canReadFriends = false;
    var friendCountHint = 0;

    if (userId != null && userId.isNotEmpty) {
      final userProfile = await _userService.getUserProfile(userId);
      friendCountHint = (userProfile?['friendsCount'] as num?)?.toInt() ?? 0;
      canReadFriends = await _authService.ensureFirebaseSessionForKakao(userId);
    }

    if (!mounted) return;
    setState(() {
      _currentUserId = userId;
      _isAuthReady = true;
      _canReadFriends = canReadFriends;
      _friendCountHint = friendCountHint;
    });
  }

  void _openFriendProfile(FriendListItem item) {
    HapticFeedback.selectionClick();
    Navigator.of(context, rootNavigator: true).pushNamed(
      RouteNames.profileSpecificDetail,
      arguments: ProfileCardArgs.fromChat(userId: item.friendUserId),
    );
  }

  String _formatAddedAt(DateTime? dateTime) {
    if (dateTime == null) return '추가일 정보 없음';
    final month = dateTime.month.toString().padLeft(2, '0');
    final day = dateTime.day.toString().padLeft(2, '0');
    return '${dateTime.year}.$month.$day 친구가 되었어요';
  }

  bool _isPermissionError(Object? error) {
    if (error is FirebaseException) {
      return error.code == 'permission-denied';
    }
    return false;
  }

  bool get _looksLikeNoFriendsYet => _friendCountHint <= 0;

  Widget _buildEmptyState() {
    return const _StateMessage(
      icon: CupertinoIcons.person_2,
      title: '아직 추가된 친구가 없어요',
      subtitle: '친구 초대 링크를 보내 설레연 친구를 만들어보세요',
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.surface.withValues(alpha: 0.92),
        border: const Border(
          bottom: BorderSide(color: _AppColors.line, width: 0.5),
        ),
        middle: const Text(
          '친구 목록',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            if (widget.onBack != null) {
              widget.onBack!();
              return;
            }
            Navigator.of(context).maybePop();
          },
          child: const Icon(
            CupertinoIcons.back,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: _currentUserId == null
            ? const Center(child: CupertinoActivityIndicator())
            : !_isAuthReady
                ? const Center(child: CupertinoActivityIndicator())
                : !_canReadFriends
                    ? (_looksLikeNoFriendsYet
                        ? _buildEmptyState()
                        : const _StateMessage(
                            icon: CupertinoIcons.lock_circle,
                            title: '친구 목록을 열 수 없어요',
                            subtitle: '학교 이메일 인증이 완료된 계정으로 다시 로그인해주세요',
                          ))
                    : StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
                        stream: _friendService.friendsStream(_currentUserId!),
                        builder: (context, snapshot) {
                          if (snapshot.hasError) {
                            if (_isPermissionError(snapshot.error) &&
                                _looksLikeNoFriendsYet) {
                              return _buildEmptyState();
                            }

                            return const _StateMessage(
                              icon: CupertinoIcons.exclamationmark_triangle,
                              title: '친구 목록을 불러오지 못했어요',
                              subtitle: '잠시 후 다시 시도해주세요',
                            );
                          }

                          if (!snapshot.hasData) {
                            return const Center(
                              child: CupertinoActivityIndicator(),
                            );
                          }

                          final docs = snapshot.data!.docs;
                          if (docs.isEmpty) {
                            return _buildEmptyState();
                          }

                          return FutureBuilder<List<FriendListItem>>(
                            future: _friendService.hydrateFriends(docs),
                            builder: (context, friendsSnapshot) {
                              if (friendsSnapshot.connectionState ==
                                      ConnectionState.waiting &&
                                  !friendsSnapshot.hasData) {
                                return const Center(
                                  child: CupertinoActivityIndicator(),
                                );
                              }

                              final friends =
                                  friendsSnapshot.data ??
                                  const <FriendListItem>[];
                              if (friends.isEmpty) {
                                return const _StateMessage(
                                  icon: CupertinoIcons
                                      .person_crop_circle_badge_xmark,
                                  title: '표시할 친구 정보가 없어요',
                                  subtitle: '프로필 정보가 준비되면 여기서 확인할 수 있어요',
                                );
                              }

                              return ListView.separated(
                                padding:
                                    const EdgeInsets.fromLTRB(20, 16, 20, 24),
                                itemCount: friends.length,
                                separatorBuilder: (_, __) =>
                                    const SizedBox(height: 12),
                                itemBuilder: (context, index) {
                                  final item = friends[index];
                                  return _FriendTile(
                                    item: item,
                                    addedAtText: _formatAddedAt(item.createdAt),
                                    onTap: () => _openFriendProfile(item),
                                  );
                                },
                              );
                            },
                          );
                        },
                      ),
      ),
    );
  }
}

class _FriendTile extends StatelessWidget {
  final FriendListItem item;
  final String addedAtText;
  final VoidCallback onTap;

  const _FriendTile({
    required this.item,
    required this.addedAtText,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final subtitleParts = <String>[
      if (item.universityName.isNotEmpty) item.universityName,
      if (item.major.isNotEmpty) item.major,
    ];

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: _AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: _AppColors.line),
        ),
        child: Row(
          children: [
            _Avatar(imageUrl: item.imageUrl, fallbackText: item.name),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  if (subtitleParts.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      subtitleParts.join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ],
                  const SizedBox(height: 6),
                  Text(
                    addedAtText,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      color: _AppColors.textSub,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(
              CupertinoIcons.chevron_right,
              size: 18,
              color: _AppColors.empty,
            ),
          ],
        ),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  final String imageUrl;
  final String fallbackText;

  const _Avatar({
    required this.imageUrl,
    required this.fallbackText,
  });

  @override
  Widget build(BuildContext context) {
    final normalized = fallbackText.trim();
    final initial = normalized.isNotEmpty ? normalized.substring(0, 1) : '?';

    if (imageUrl.isEmpty) {
      return Container(
        width: 56,
        height: 56,
        decoration: const BoxDecoration(
          color: Color(0xFFFCE5EE),
          shape: BoxShape.circle,
        ),
        alignment: Alignment.center,
        child: Text(
          initial,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: _AppColors.primary,
          ),
        ),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: Image.network(
        imageUrl,
        width: 56,
        height: 56,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: 56,
          height: 56,
          decoration: const BoxDecoration(
            color: Color(0xFFFCE5EE),
            shape: BoxShape.circle,
          ),
          alignment: Alignment.center,
          child: Text(
            initial,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: _AppColors.primary,
            ),
          ),
        ),
      ),
    );
  }
}

class _StateMessage extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _StateMessage({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 42, color: _AppColors.empty),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                height: 1.5,
                color: _AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
