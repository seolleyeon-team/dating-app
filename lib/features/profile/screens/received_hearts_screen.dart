// =============================================================================
// 받은 하트 목록 화면
// 경로: lib/features/profile/screens/received_hearts_screen.dart
//
// interactions 컬렉션에서 action=='like' && toUserId==currentUid 조회
// =============================================================================

import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/interaction_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/widgets/chat_unlocked_profile_avatar.dart';
import '../../matching/models/profile_card_args.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF994D60);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
}

const String _kFontFamily = 'Noto Sans KR';

// =============================================================================
// Hydrated heart profile view model
// =============================================================================
class _HeartItem {
  final String interactionId;
  final String otherUserId;
  final DateTime? createdAt;
  final String name;
  final String imageUrl;
  final String department;
  final String university;
  final int age;

  const _HeartItem({
    required this.interactionId,
    required this.otherUserId,
    this.createdAt,
    required this.name,
    required this.imageUrl,
    required this.department,
    required this.university,
    required this.age,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class ReceivedHeartsScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onReveal;
  final int? selectedNavIndex;
  final Function(int)? onNavTap;

  const ReceivedHeartsScreen({
    super.key,
    this.onBack,
    this.onReveal,
    this.selectedNavIndex,
    this.onNavTap,
  });

  @override
  State<ReceivedHeartsScreen> createState() => _ReceivedHeartsScreenState();
}

class _ReceivedHeartsScreenState extends State<ReceivedHeartsScreen> {
  final InteractionService _interactionService = InteractionService();
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  String? _currentUserId;
  Stream<List<Map<String, dynamic>>>? _likesStream;

  final Map<String, Map<String, dynamic>?> _profileCache = {};

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final uid = await _storageService.getKakaoUserId();
    if (!mounted || uid == null || uid.isEmpty) return;
    setState(() {
      _currentUserId = uid;
      _likesStream = _interactionService.watchLikesReceived(uid);
    });
  }

  Future<List<_HeartItem>> _hydrate(List<Map<String, dynamic>> interactions) async {
    // dedupe: 같은 fromUserId 중 최신 1개만
    final Map<String, Map<String, dynamic>> deduped = {};
    for (final doc in interactions) {
      final otherId = doc['fromUserId'] as String? ?? '';
      if (otherId.isEmpty) continue;
      if (!deduped.containsKey(otherId)) {
        deduped[otherId] = doc;
      }
    }

    final items = <_HeartItem>[];
    for (final entry in deduped.entries) {
      final otherId = entry.key;
      final doc = entry.value;

      if (!_profileCache.containsKey(otherId)) {
        _profileCache[otherId] = await _userService.getUserProfile(otherId);
      }
      final profile = _profileCache[otherId];
      final onboarding = profile?['onboarding'] as Map?;

      final nickname = profile?['nickname'] as String? ??
          (onboarding?['nickname'] as String?) ??
          '익명';

      final photoUrls = onboarding?['photoUrls'];
      final imageUrl = (photoUrls is List && photoUrls.isNotEmpty)
          ? photoUrls.first as String
          : '';

      int age = 0;
      final birthYear = onboarding?['birthYear'];
      if (birthYear != null) {
        final y = int.tryParse(birthYear.toString());
        if (y != null) age = DateTime.now().year - y;
      }

      final major = onboarding?['major'] as String? ?? '';
      final university = onboarding?['university'] as String? ?? '';

      DateTime? createdAt;
      final ts = doc['createdAt'];
      if (ts is Timestamp) createdAt = ts.toDate();

      items.add(_HeartItem(
        interactionId: doc['id'] as String? ?? '',
        otherUserId: otherId,
        createdAt: createdAt,
        name: nickname,
        imageUrl: imageUrl,
        department: major,
        university: university,
        age: age,
      ));
    }
    return items;
  }

  String _formatDate(DateTime? dt) {
    if (dt == null) return '';
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';
    return '${dt.month}월 ${dt.day}일';
  }

  void _onProfileTap(String otherId) {
    if (widget.onReveal != null) {
      widget.onReveal!(otherId);
    } else {
      Navigator.of(context, rootNavigator: true).pushNamed(
        RouteNames.profileSpecificDetail,
        arguments: ProfileCardArgs.fromChat(userId: otherId),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.surfaceLight,
      child: Stack(
        children: [
          // 배경 그라데이션
          Positioned(
            top: 0, left: 0, right: 0, height: 256,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.primary.withValues(alpha: 0.1),
                    CupertinoColors.white.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          _currentUserId == null
              ? const Center(child: CupertinoActivityIndicator())
              : StreamBuilder<List<Map<String, dynamic>>>(
                  stream: _likesStream,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CupertinoActivityIndicator());
                    }
                    if (snapshot.hasError) {
                      return Center(
                        child: Text(
                          '데이터를 불러올 수 없어요',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            color: _AppColors.gray500,
                          ),
                        ),
                      );
                    }
                    final interactions = snapshot.data ?? [];
                    return FutureBuilder<List<_HeartItem>>(
                      future: _hydrate(interactions),
                      builder: (context, hydSnap) {
                        final items = hydSnap.data ?? [];
                        return CustomScrollView(
                          physics: const BouncingScrollPhysics(),
                          slivers: [
                            // 헤더
                            SliverToBoxAdapter(
                              child: _Header(
                                onBack: widget.onBack,
                                count: items.length,
                              ),
                            ),
                            // 빈 상태
                            if (items.isEmpty && hydSnap.connectionState == ConnectionState.done)
                              SliverFillRemaining(
                                hasScrollBody: false,
                                child: Center(
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(
                                        CupertinoIcons.heart,
                                        size: 48,
                                        color: _AppColors.gray400.withValues(alpha: 0.5),
                                      ),
                                      const SizedBox(height: 16),
                                      const Text(
                                        '받은 좋아요가 아직 없어요',
                                        style: TextStyle(
                                          fontFamily: _kFontFamily,
                                          fontSize: 15,
                                          color: _AppColors.gray500,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              )
                            else
                              // 리스트
                              SliverPadding(
                                padding: EdgeInsets.fromLTRB(
                                    16, 8, 16, bottomPadding + 24),
                                sliver: SliverList(
                                  delegate: SliverChildBuilderDelegate(
                                    (context, index) => Padding(
                                      padding: const EdgeInsets.only(bottom: 12),
                                      child: _ReceivedHeartCard(
                                        item: items[index],
                                        currentUserId: _currentUserId!,
                                        dateText: _formatDate(items[index].createdAt),
                                        onTap: () => _onProfileTap(items[index].otherUserId),
                                      ),
                                    ),
                                    childCount: items.length,
                                  ),
                                ),
                              ),
                          ],
                        );
                      },
                    );
                  },
                ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onBack;
  final int count;

  const _Header({this.onBack, this.count = 0});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Row(
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                HapticFeedback.lightImpact();
                if (onBack != null) {
                  onBack!();
                } else {
                  Navigator.of(context).pop();
                }
              },
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: CupertinoColors.black.withValues(alpha: 0.05),
                ),
                child: const Icon(
                  CupertinoIcons.back,
                  size: 20,
                  color: _AppColors.textMain,
                ),
              ),
            ),
            Expanded(
              child: Text(
                '받은 좋아요 ($count)',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                  color: _AppColors.textMain,
                ),
              ),
            ),
            const SizedBox(width: 40),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 실제 프로필 카드 (받은 좋아요)
// =============================================================================
class _ReceivedHeartCard extends StatelessWidget {
  final _HeartItem item;
  final String currentUserId;
  final String dateText;
  final VoidCallback? onTap;

  const _ReceivedHeartCard({
    required this.item,
    required this.currentUserId,
    required this.dateText,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.selectionClick();
        onTap?.call();
      },
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _AppColors.primary.withValues(alpha: 0.08),
          ),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.04),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            // 프로필 이미지
            _ProfileAvatar(
              currentUserId: currentUserId,
              targetUserId: item.otherUserId,
              imageUrl: item.imageUrl,
            ),
            const SizedBox(width: 16),
            // 콘텐츠
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Flexible(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Flexible(
                              child: Text(
                                item.name,
                                style: const TextStyle(
                                  fontFamily: _kFontFamily,
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                  color: _AppColors.textMain,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 6),
                            const Icon(
                              CupertinoIcons.heart_fill,
                              size: 14,
                              color: _AppColors.primary,
                            ),
                          ],
                        ),
                      ),
                      if (dateText.isNotEmpty)
                        Text(
                          dateText,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.3,
                            color: _AppColors.textMain,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    [
                      if (item.department.isNotEmpty) item.department,
                      if (item.age > 0) '${item.age}세',
                      if (item.university.isNotEmpty) item.university,
                    ].join(' • '),
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      color: _AppColors.textSub,
                    ),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 4),
            const Icon(
              CupertinoIcons.chevron_right,
              size: 20,
              color: _AppColors.gray400,
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 프로필 아바타
// =============================================================================
class _ProfileAvatar extends StatelessWidget {
  final String currentUserId;
  final String targetUserId;
  final String imageUrl;

  const _ProfileAvatar({
    required this.currentUserId,
    required this.targetUserId,
    required this.imageUrl,
  });

  @override
  Widget build(BuildContext context) {
    return ChatUnlockedProfileAvatar(
      currentUserId: currentUserId,
      targetUserId: targetUserId,
      imageUrl: imageUrl,
      size: 72,
      borderWidth: 2,
      borderColor: _AppColors.primary.withValues(alpha: 0.15),
      backgroundColor: _AppColors.gray100,
      placeholderIconColor: _AppColors.gray400,
      placeholderIconSize: 32,
    );
  }
}
