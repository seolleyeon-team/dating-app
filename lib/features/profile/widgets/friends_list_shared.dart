import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';

import '../../../services/friend_service.dart';

/// 친구 목록 / 친구 피커 공통 색상
class FriendsListSharedColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color background = Color(0xFFF8F8FA);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF8B8B94);
  static const Color line = Color(0xFFE9E9EE);
  static const Color empty = Color(0xFFB7B7C2);
}

enum FriendsListStreamMode {
  browse,
  picker,
}

class FriendsListStreamBody extends StatelessWidget {
  final String currentUserId;
  final FriendService friendService;
  final FriendsListStreamMode mode;
  final Set<String> excludedFriendUserIds;
  final Set<String> disabledFriendUserIds;
  final Set<String> selectedFriendUserIds;
  final void Function(FriendListItem item)? onBrowseTap;
  final void Function(FriendListItem item, bool willSelect)? onPickerToggle;
  final String Function(DateTime? dateTime) formatAddedAt;

  /// 친구 수 힌트가 0이고 permission-denied일 때, 빈 목록 UI로 완화 (기존 friends_list 동작)
  final bool emptyOnPermissionDeniedWhenNoFriendsHint;
  final int friendCountHint;

  /// picker 전용: 추가 선택 가능한 최대 명수 (팀 남은 자리). browse에서는 -1
  final int pickerMaxAdditionalSelections;
  final int pickerSelectedCount;

  const FriendsListStreamBody({
    super.key,
    required this.currentUserId,
    required this.friendService,
    this.mode = FriendsListStreamMode.browse,
    this.excludedFriendUserIds = const {},
    this.disabledFriendUserIds = const {},
    this.selectedFriendUserIds = const {},
    this.onBrowseTap,
    this.onPickerToggle,
    required this.formatAddedAt,
    this.emptyOnPermissionDeniedWhenNoFriendsHint = false,
    this.friendCountHint = 0,
    this.pickerMaxAdditionalSelections = -1,
    this.pickerSelectedCount = 0,
  });

  bool _isPermissionError(Object? error) {
    if (error is FirebaseException) {
      return error.code == 'permission-denied';
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
      stream: friendService.friendsStream(currentUserId),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          if (emptyOnPermissionDeniedWhenNoFriendsHint &&
              _isPermissionError(snapshot.error) &&
              friendCountHint <= 0) {
            return const FriendsListEmptyMessage(
              icon: CupertinoIcons.person_2,
              title: '아직 추가된 친구가 없어요',
              subtitle: '친구 초대 링크를 보내 설레연 친구를 만들어보세요',
            );
          }
          return FriendsListEmptyMessage(
            icon: CupertinoIcons.exclamationmark_triangle,
            title: '친구 목록을 불러오지 못했어요',
            subtitle: _isPermissionError(snapshot.error)
                ? '학교 이메일 인증이 완료된 계정으로 다시 로그인해주세요'
                : '잠시 후 다시 시도해주세요',
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CupertinoActivityIndicator());
        }
        final docs = snapshot.data!.docs;
        if (docs.isEmpty) {
          return const FriendsListEmptyMessage(
            icon: CupertinoIcons.person_2,
            title: '아직 추가된 친구가 없어요',
            subtitle: '친구 초대 링크를 보내 설레연 친구를 만들어보세요',
          );
        }

        return FutureBuilder<List<FriendListItem>>(
          future: friendService.hydrateFriends(docs),
          builder: (context, friendsSnapshot) {
            if (friendsSnapshot.connectionState == ConnectionState.waiting &&
                !friendsSnapshot.hasData) {
              return const Center(child: CupertinoActivityIndicator());
            }
            var friends = friendsSnapshot.data ?? const <FriendListItem>[];
            friends = friends
                .where(
                  (f) => !excludedFriendUserIds.contains(f.friendUserId),
                )
                .toList();
            if (friends.isEmpty) {
              return const FriendsListEmptyMessage(
                icon: CupertinoIcons.person_crop_circle_badge_xmark,
                title: '선택할 수 있는 친구가 없어요',
                subtitle: '팀에 포함되지 않은 친구만 여기에서 고를 수 있어요',
              );
            }

            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
              itemCount: friends.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final item = friends[index];
                final addedAtText = formatAddedAt(item.createdAt);
                final isPicker = mode == FriendsListStreamMode.picker;
                final selected =
                    selectedFriendUserIds.contains(item.friendUserId);
                final atPickLimit = isPicker &&
                    pickerMaxAdditionalSelections >= 0 &&
                    !selected &&
                    pickerSelectedCount >= pickerMaxAdditionalSelections;
                final disabled = disabledFriendUserIds
                        .contains(item.friendUserId) ||
                    atPickLimit;

                return FriendListTileWidget(
                  item: item,
                  addedAtText: addedAtText,
                  mode: mode,
                  selected: selected,
                  disabled: disabled,
                  onTap: () {
                    if (isPicker) {
                      if (disabled) return;
                      onPickerToggle?.call(item, !selected);
                    } else {
                      onBrowseTap?.call(item);
                    }
                  },
                );
              },
            );
          },
        );
      },
    );
  }
}

class FriendListTileWidget extends StatelessWidget {
  final FriendListItem item;
  final String addedAtText;
  final FriendsListStreamMode mode;
  final bool selected;
  final bool disabled;
  final VoidCallback onTap;

  const FriendListTileWidget({
    super.key,
    required this.item,
    required this.addedAtText,
    required this.mode,
    required this.selected,
    required this.disabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final subtitleParts = <String>[
      if (item.universityName.isNotEmpty) item.universityName,
      if (item.major.isNotEmpty) item.major,
    ];
    final isPicker = mode == FriendsListStreamMode.picker;
    final opacity = disabled ? 0.45 : 1.0;

    return Opacity(
      opacity: opacity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: disabled ? null : onTap,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: FriendsListSharedColors.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: selected && isPicker
                  ? FriendsListSharedColors.primary
                  : FriendsListSharedColors.line,
              width: selected && isPicker ? 1.5 : 1,
            ),
          ),
          child: Row(
            children: [
              FriendAvatarWidget(
                imageUrl: item.imageUrl,
                fallbackText: item.name,
              ),
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
                        color: FriendsListSharedColors.textMain,
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
                          color: FriendsListSharedColors.textSub,
                        ),
                      ),
                    ],
                    const SizedBox(height: 6),
                    Text(
                      addedAtText,
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        color: FriendsListSharedColors.textSub,
                      ),
                    ),
                  ],
                ),
              ),
              if (isPicker) ...[
                const SizedBox(width: 8),
                Icon(
                  selected
                      ? CupertinoIcons.checkmark_circle_fill
                      : CupertinoIcons.circle,
                  size: 24,
                  color: selected
                      ? FriendsListSharedColors.primary
                      : FriendsListSharedColors.empty,
                ),
              ] else ...[
                const SizedBox(width: 8),
                const Icon(
                  CupertinoIcons.chevron_right,
                  size: 18,
                  color: FriendsListSharedColors.empty,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class FriendAvatarWidget extends StatelessWidget {
  final String imageUrl;
  final String fallbackText;

  const FriendAvatarWidget({
    super.key,
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
            color: FriendsListSharedColors.primary,
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
              color: FriendsListSharedColors.primary,
            ),
          ),
        ),
      ),
    );
  }
}

class FriendsListEmptyMessage extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const FriendsListEmptyMessage({
    super.key,
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
            Icon(icon, size: 42, color: FriendsListSharedColors.empty),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: FriendsListSharedColors.textMain,
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
                color: FriendsListSharedColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
