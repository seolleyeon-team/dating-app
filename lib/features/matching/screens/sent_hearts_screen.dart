// =============================================================================
// 내가 보낸 호감 목록 화면
// 경로: lib/features/matching/screens/sent_hearts_screen.dart
//
// interactions 컬렉션에서 action=='like' && fromUserId==currentUid 조회
// =============================================================================

import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/interaction_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../models/profile_card_args.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEC3C68);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textPrimary = Color(0xFF1B0E11);
  static const Color textSecondary = Color(0xFF994D60);
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
  final int age;
  final List<String> tags;

  const _HeartItem({
    required this.interactionId,
    required this.otherUserId,
    this.createdAt,
    required this.name,
    required this.imageUrl,
    required this.department,
    required this.age,
    this.tags = const [],
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class SentHeartsScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final VoidCallback? onFilter;
  final Function(String profileId)? onProfileTap;
  final Function(int navIndex)? onNavTap;

  const SentHeartsScreen({
    super.key,
    this.onBack,
    this.onFilter,
    this.onProfileTap,
    this.onNavTap,
  });

  @override
  State<SentHeartsScreen> createState() => _SentHeartsScreenState();
}

class _SentHeartsScreenState extends State<SentHeartsScreen> {
  final InteractionService _interactionService = InteractionService();
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  String? _currentUserId;
  Stream<List<Map<String, dynamic>>>? _likesStream;

  // 프로필 캐시
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
      _likesStream = _interactionService.watchLikesSent(uid);
    });
  }

  /// interactions 리스트를 dedupe + profile hydrate
  Future<List<_HeartItem>> _hydrate(List<Map<String, dynamic>> interactions) async {
    // dedupe: 같은 toUserId 중 최신 1개만
    final Map<String, Map<String, dynamic>> deduped = {};
    for (final doc in interactions) {
      final otherId = doc['toUserId'] as String? ?? '';
      if (otherId.isEmpty) continue;
      if (!deduped.containsKey(otherId)) {
        deduped[otherId] = doc;
      }
    }

    final items = <_HeartItem>[];
    for (final entry in deduped.entries) {
      final otherId = entry.key;
      final doc = entry.value;

      // profile fetch with cache
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

      List<String> tags = [];
      if (onboarding?['keywords'] is List) {
        tags.addAll(List<String>.from(onboarding!['keywords']));
      }
      if (onboarding?['interests'] is List) {
        tags.addAll(List<String>.from(onboarding!['interests']));
      }

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
        age: age,
        tags: tags.take(3).toList(),
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
    if (widget.onProfileTap != null) {
      widget.onProfileTap!(otherId);
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
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 글로우
          Positioned(
            top: -60,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: MediaQuery.of(context).size.width * 1.4,
                height: 300,
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    colors: [
                      _AppColors.primary.withValues(alpha: 0.06),
                      _AppColors.primary.withValues(alpha: 0),
                    ],
                  ),
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
                            fontFamily: _kFontFamily,
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
                            SliverToBoxAdapter(
                              child: _Header(
                                onBack: widget.onBack,
                                count: items.length,
                              ),
                            ),
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
                                        '보낸 좋아요가 아직 없어요',
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
                              SliverPadding(
                                padding: EdgeInsets.fromLTRB(
                                    16, 8, 16, bottomPadding + 24),
                                sliver: SliverList(
                                  delegate: SliverChildBuilderDelegate(
                                    (context, index) => Padding(
                                      padding: const EdgeInsets.only(bottom: 12),
                                      child: _ProfileListItem(
                                        item: items[index],
                                        dateText:
                                            _formatDate(items[index].createdAt),
                                        onTap: () => _onProfileTap(
                                            items[index].otherUserId),
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
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: BoxDecoration(
          color: _AppColors.backgroundLight.withValues(alpha: 0.95),
          border: Border(
            bottom: BorderSide(
              color: _AppColors.primary.withValues(alpha: 0.05),
            ),
          ),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: CupertinoButton(
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
                    color: _AppColors.textPrimary,
                  ),
                ),
              ),
            ),
            Text(
              '내가 보낸 호감 ($count)',
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textPrimary,
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
// 프로필 리스트 아이템
// =============================================================================
class _ProfileListItem extends StatelessWidget {
  final _HeartItem item;
  final String dateText;
  final VoidCallback? onTap;

  const _ProfileListItem({
    required this.item,
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
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.03),
              blurRadius: 10,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          children: [
            // 프로필 이미지
            _ProfileAvatar(imageUrl: item.imageUrl),
            const SizedBox(width: 16),
            // 콘텐츠
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Flexible(
                        child: Text(
                          item.name,
                          style: const TextStyle(
                            fontFamily: _kFontFamily,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textPrimary,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 8),
                      if (dateText.isNotEmpty)
                        Text(
                          dateText,
                          style: const TextStyle(
                            fontFamily: _kFontFamily,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.gray400,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    [
                      if (item.department.isNotEmpty) item.department,
                      if (item.age > 0) '${item.age}세',
                    ].join(' • '),
                    style: const TextStyle(
                      fontFamily: _kFontFamily,
                      fontSize: 12,
                      color: _AppColors.textSecondary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (item.tags.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    _TagRow(tags: item.tags),
                  ],
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
  final String imageUrl;

  const _ProfileAvatar({required this.imageUrl});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: _AppColors.primary.withValues(alpha: 0.1),
          width: 2,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: imageUrl.isNotEmpty
          ? Image.network(
              imageUrl,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => _placeholder(),
            )
          : _placeholder(),
    );
  }

  Widget _placeholder() {
    return Container(
      color: _AppColors.gray100,
      child: const Icon(
        CupertinoIcons.person_fill,
        size: 32,
        color: _AppColors.gray400,
      ),
    );
  }
}

// =============================================================================
// 태그 Row
// =============================================================================
class _TagRow extends StatelessWidget {
  final List<String> tags;

  const _TagRow({required this.tags});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 4,
      children: tags.map((tag) {
        final label = tag.startsWith('#') ? tag : '#$tag';
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: _AppColors.primary.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            label,
            style: const TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: _AppColors.primary,
            ),
          ),
        );
      }).toList(),
    );
  }
}
