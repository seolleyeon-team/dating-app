import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/constants/app_colors.dart';

import '../../../services/ask_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/utils/profile_display_image_resolver.dart';
import '../../../shared/widgets/chat_unlocked_profile_avatar.dart';

const String _kFontFamily = 'Noto Sans KR';

class _C {
  static const Color primary = Color(0xFFF0428B);
  static const Color bg = Color(0xFFF9F9F9);
  static const Color white = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1A1A1A);
  static const Color textSub = Color(0xFF8E8E93);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color unreadDot = Color(0xFFF0428B);
}

class AsksInboxScreen extends StatefulWidget {
  const AsksInboxScreen({super.key});

  @override
  State<AsksInboxScreen> createState() => _AsksInboxScreenState();
}

class _AsksInboxScreenState extends State<AsksInboxScreen> {
  final AskService _askService = AskService();
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  String? _currentUserId;
  int _tabIndex = 0; // 0: 받은 무물, 1: 보낸 무물

  @override
  void initState() {
    super.initState();
    _loadUser();
  }

  Future<void> _loadUser() async {
    final uid = await _storageService.getKakaoUserId();
    if (!mounted) return;
    setState(() => _currentUserId = uid);
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final background = dark ? AppColorsDark.background : _C.bg;
    final surface = dark ? AppColorsDark.surface : _C.white;
    final divider = dark ? AppColorsDark.divider : _C.gray200;
    return CupertinoPageScaffold(
      backgroundColor: background,
      navigationBar: CupertinoNavigationBar(
        middle: const Text(
          '무물함',
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontWeight: FontWeight.w700,
          ),
        ),
        backgroundColor: surface.withValues(alpha: 0.9),
        border: Border(
          bottom: BorderSide(color: divider.withValues(alpha: 0.5)),
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 16),
            _buildSegmentedControl(),
            const SizedBox(height: 12),
            Expanded(
              child: _currentUserId == null || _currentUserId!.isEmpty
                  ? const Center(
                      child: Text(
                        '로그인 정보를 확인할 수 없어요',
                        style: TextStyle(
                          fontFamily: _kFontFamily,
                          color: _C.textSub,
                        ),
                      ),
                    )
                  : _tabIndex == 0
                  ? _AskList(
                      stream: _askService.receivedAsksStream(_currentUserId!),
                      emptyIcon: CupertinoIcons.tray,
                      emptyTitle: '아직 받은 무물이 없어요',
                      emptySub: '누군가 궁금해할 때까지 조금만 기다려주세요',
                      isReceived: true,
                      currentUserId: _currentUserId!,
                      askService: _askService,
                      userService: _userService,
                    )
                  : _AskList(
                      stream: _askService.sentAsksStream(_currentUserId!),
                      emptyIcon: CupertinoIcons.paperplane,
                      emptyTitle: '아직 보낸 무물이 없어요',
                      emptySub: '프로필에서 궁금한 상대에게 질문을 보내보세요',
                      isReceived: false,
                      currentUserId: _currentUserId!,
                      askService: _askService,
                      userService: _userService,
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSegmentedControl() {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: CupertinoSlidingSegmentedControl<int>(
        groupValue: _tabIndex,
        backgroundColor: dark ? AppColorsDark.surfaceVariant : _C.gray100,
        thumbColor: dark ? AppColorsDark.surface : _C.white,
        children: const {
          0: Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Text(
              '받은 무물',
              style: TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          1: Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Text(
              '보낸 무물',
              style: TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        },
        onValueChanged: (val) {
          if (val != null) {
            HapticFeedback.selectionClick();
            setState(() => _tabIndex = val);
          }
        },
      ),
    );
  }
}

// =============================================================================
// 무물 리스트
// =============================================================================
class _AskList extends StatelessWidget {
  final Stream<QuerySnapshot<Map<String, dynamic>>> stream;
  final IconData emptyIcon;
  final String emptyTitle;
  final String emptySub;
  final bool isReceived;
  final String currentUserId;
  final AskService askService;
  final UserService userService;

  const _AskList({
    required this.stream,
    required this.emptyIcon,
    required this.emptyTitle,
    required this.emptySub,
    required this.isReceived,
    required this.currentUserId,
    required this.askService,
    required this.userService,
  });

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
      stream: stream,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CupertinoActivityIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Text(
                '불러오지 못했어요.\n잠시 후 다시 시도해주세요.',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  color: _C.textSub,
                  height: 1.5,
                ),
              ),
            ),
          );
        }

        final docs = snapshot.data?.docs ?? [];
        if (docs.isEmpty) {
          return _EmptyState(
            icon: emptyIcon,
            title: emptyTitle,
            subtitle: emptySub,
          );
        }

        return ListView.separated(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          itemCount: docs.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, index) {
            final doc = docs[index];
            final data = doc.data();
            return _AskCard(
              askId: doc.id,
              data: data,
              isReceived: isReceived,
              currentUserId: currentUserId,
              askService: askService,
              userService: userService,
            );
          },
        );
      },
    );
  }
}

// =============================================================================
// 무물 카드
// =============================================================================
class _AskCard extends StatelessWidget {
  final String askId;
  final Map<String, dynamic> data;
  final bool isReceived;
  final String currentUserId;
  final AskService askService;
  final UserService userService;

  const _AskCard({
    required this.askId,
    required this.data,
    required this.isReceived,
    required this.currentUserId,
    required this.askService,
    required this.userService,
  });

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final surface = dark ? AppColorsDark.surface : _C.white;
    final unreadSurface = dark ? const Color(0xFF33212C) : _C.pink50;
    final border = dark ? AppColorsDark.border : _C.gray200;
    final text = data['text']?.toString() ?? '';
    final status = data['status']?.toString() ?? 'sent';
    final isUnread = isReceived && status == 'sent';

    final otherUserId =
        (isReceived ? data['fromUserId'] : data['toUserId'])?.toString() ?? '';

    final createdAt = data['createdAt'];
    final timeText = _formatTime(createdAt);

    // P1-10: the counterpart's identity comes from the server-owned public
    // profile, never from a client-written snapshot on the ask document.
    return _CounterpartProfile(
      userService: userService,
      userId: otherUserId,
      legacyNickname: AskService.legacyNicknameFallback(
        data,
        isReceived: isReceived,
      ),
      builder: (context, counterpart) {
        final nickname = counterpart.nickname;
        final avatarUrl = counterpart.avatarUrl;
        final university = counterpart.university;
        return _buildCard(
          context,
          dark: dark,
          surface: surface,
          unreadSurface: unreadSurface,
          border: border,
          text: text,
          isUnread: isUnread,
          nickname: nickname,
          avatarUrl: avatarUrl,
          university: university,
          otherUserId: otherUserId,
          timeText: timeText,
        );
      },
    );
  }

  Widget _buildCard(
    BuildContext context, {
    required bool dark,
    required Color surface,
    required Color unreadSurface,
    required Color border,
    required String text,
    required bool isUnread,
    required String nickname,
    required String avatarUrl,
    required String university,
    required String otherUserId,
    required String timeText,
  }) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => _showDetail(context, text, isUnread),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isUnread ? unreadSurface : surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isUnread
                ? _C.primary.withValues(alpha: 0.15)
                : border.withValues(alpha: 0.6),
          ),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.03),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _Avatar(
              url: avatarUrl,
              currentUserId: currentUserId,
              targetUserId: otherUserId,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          nickname.isNotEmpty ? nickname : '사용자',
                          style: TextStyle(
                            fontFamily: _kFontFamily,
                            fontSize: 15,
                            fontWeight: isUnread
                                ? FontWeight.w700
                                : FontWeight.w600,
                            color: _C.textMain,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (isUnread)
                        Container(
                          width: 8,
                          height: 8,
                          margin: const EdgeInsets.only(left: 6),
                          decoration: const BoxDecoration(
                            color: _C.unreadDot,
                            shape: BoxShape.circle,
                          ),
                        ),
                    ],
                  ),
                  if (university.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      university,
                      style: const TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 12,
                        color: _C.gray400,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 6),
                  Text(
                    text,
                    style: TextStyle(
                      fontFamily: _kFontFamily,
                      fontSize: 14,
                      color: isUnread ? _C.textMain : _C.textSub,
                      fontWeight: isUnread ? FontWeight.w500 : FontWeight.w400,
                      height: 1.4,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    timeText,
                    style: const TextStyle(
                      fontFamily: _kFontFamily,
                      fontSize: 11,
                      color: _C.gray400,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showDetail(BuildContext context, String text, bool isUnread) {
    if (isUnread) {
      askService
          .markAsRead(askId)
          .catchError(
            (e) => debugPrint(
              '[AskInbox] markAsRead failed: ${PrivacyLogUtils.errorSummary(e)}',
            ),
          );
    }

    showCupertinoModalPopup(
      context: context,
      builder: (ctx) => _AskDetailSheet(
        data: data,
        isReceived: isReceived,
        currentUserId: currentUserId,
        userService: userService,
      ),
    );
  }

  String _formatTime(dynamic ts) {
    DateTime? dt;
    if (ts is Timestamp) {
      dt = ts.toDate().toLocal();
    }
    if (dt == null) return '';

    final now = DateTime.now();
    final diff = now.difference(dt);

    if (diff.inMinutes < 1) return '방금 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';

    return '${dt.month}/${dt.day}';
  }
}

// =============================================================================
// 아바타
// =============================================================================
class _Avatar extends StatelessWidget {
  final String url;
  final String currentUserId;
  final String targetUserId;

  const _Avatar({
    required this.url,
    required this.currentUserId,
    required this.targetUserId,
  });

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return ChatUnlockedProfileAvatar(
      currentUserId: currentUserId,
      targetUserId: targetUserId,
      imageUrl: url,
      size: 48,
      borderWidth: 1,
      borderColor: (dark ? AppColorsDark.border : _C.gray200).withValues(
        alpha: 0.5,
      ),
      backgroundColor: dark ? AppColorsDark.surfaceVariant : _C.gray100,
      placeholderIconColor: dark ? AppColorsDark.textHint : _C.gray300,
      placeholderIconSize: 24,
    );
  }
}

// =============================================================================
// 무물 상세 시트
// =============================================================================
class _AskDetailSheet extends StatelessWidget {
  final Map<String, dynamic> data;
  final bool isReceived;
  final String currentUserId;

  final UserService userService;

  const _AskDetailSheet({
    required this.data,
    required this.isReceived,
    required this.currentUserId,
    required this.userService,
  });

  @override
  Widget build(BuildContext context) {
    final otherUserId =
        (isReceived ? data['fromUserId'] : data['toUserId'])?.toString() ?? '';
    return _CounterpartProfile(
      userService: userService,
      userId: otherUserId,
      legacyNickname: AskService.legacyNicknameFallback(
        data,
        isReceived: isReceived,
      ),
      builder: (context, counterpart) => _buildSheet(
        context,
        nickname: counterpart.nickname.isNotEmpty
            ? counterpart.nickname
            : '사용자',
        avatarUrl: counterpart.avatarUrl,
        university: counterpart.university,
        otherUserId: otherUserId,
      ),
    );
  }

  Widget _buildSheet(
    BuildContext context, {
    required String nickname,
    required String avatarUrl,
    required String university,
    required String otherUserId,
  }) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final surface = dark ? AppColorsDark.surface : _C.white;
    final softSurface = dark ? const Color(0xFF33212C) : _C.pink50;
    final text = data['text']?.toString() ?? '';

    final label = isReceived ? '$nickname님의 질문' : '$nickname님에게 보낸 질문';

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.6,
      ),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: _C.gray200,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              _Avatar(
                url: avatarUrl,
                currentUserId: currentUserId,
                targetUserId: otherUserId,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: _C.textMain,
                      ),
                    ),
                    if (university.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        university,
                        style: const TextStyle(
                          fontFamily: _kFontFamily,
                          fontSize: 13,
                          color: _C.gray400,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: softSurface,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              text,
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 15,
                color: _C.textMain,
                height: 1.6,
              ),
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: CupertinoButton(
              padding: const EdgeInsets.symmetric(vertical: 14),
              color: _C.gray100,
              borderRadius: BorderRadius.circular(14),
              onPressed: () => Navigator.pop(context),
              child: const Text(
                '닫기',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: _C.textSub,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// P1-10: counterpart identity from publicProfiles/{uid} (server-owned)
// =============================================================================
class _Counterpart {
  const _Counterpart({
    required this.nickname,
    required this.avatarUrl,
    required this.university,
  });

  final String nickname;
  final String avatarUrl;
  final String university;
}

class _CounterpartProfile extends StatelessWidget {
  final UserService userService;
  final String userId;
  final String legacyNickname;
  final Widget Function(BuildContext context, _Counterpart counterpart) builder;

  const _CounterpartProfile({
    required this.userService,
    required this.userId,
    required this.legacyNickname,
    required this.builder,
  });

  static _Counterpart fromPublicProfile(
    Map<String, dynamic>? profile, {
    required String legacyNickname,
  }) {
    if (profile == null) {
      // Legacy ask documents carry a client-written snapshot: only its text
      // nickname is a tolerable fallback; an image URL from it never is.
      return _Counterpart(
        nickname: legacyNickname,
        avatarUrl: '',
        university: '',
      );
    }
    final onboarding = profile['onboarding'];
    final onboardingMap = onboarding is Map
        ? Map<String, dynamic>.from(onboarding)
        : const <String, dynamic>{};
    final nickname =
        (onboardingMap['nickname'] ?? profile['nickname'])?.toString().trim() ??
        '';
    final university =
        (onboardingMap['university'] ?? profile['university'])
            ?.toString()
            .trim() ??
        '';
    return _Counterpart(
      nickname: nickname.isNotEmpty ? nickname : legacyNickname,
      avatarUrl: ProfileDisplayImageResolver.resolve(profile),
      university: university,
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: userId.isEmpty
          ? Future<Map<String, dynamic>?>.value(null)
          : userService.getPublicProfile(userId).catchError((_) => null),
      builder: (context, snapshot) => builder(
        context,
        fromPublicProfile(snapshot.data, legacyNickname: legacyNickname),
      ),
    );
  }
}

// =============================================================================
// 빈 상태
// =============================================================================
class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _EmptyState({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: _C.pink50,
                shape: BoxShape.circle,
              ),
              child: Icon(
                icon,
                size: 32,
                color: _C.primary.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              title,
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: _C.textMain,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 13,
                color: _C.textSub,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
