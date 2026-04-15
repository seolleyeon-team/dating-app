import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/ask_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/widgets/capture_protected_image.dart';

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
    return CupertinoPageScaffold(
      backgroundColor: _C.bg,
      navigationBar: CupertinoNavigationBar(
        middle: const Text(
          '무물함',
          style: TextStyle(fontFamily: _kFontFamily, fontWeight: FontWeight.w700),
        ),
        backgroundColor: _C.white.withValues(alpha: 0.9),
        border: Border(
          bottom: BorderSide(color: _C.gray200.withValues(alpha: 0.5)),
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
                          stream: _askService
                              .receivedAsksStream(_currentUserId!),
                          emptyIcon: CupertinoIcons.tray,
                          emptyTitle: '아직 받은 무물이 없어요',
                          emptySub: '누군가 궁금해할 때까지 조금만 기다려주세요',
                          isReceived: true,
                          currentUserId: _currentUserId!,
                          askService: _askService,
                          userService: _userService,
                        )
                      : _AskList(
                          stream:
                              _askService.sentAsksStream(_currentUserId!),
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
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: CupertinoSlidingSegmentedControl<int>(
        groupValue: _tabIndex,
        backgroundColor: _C.gray100,
        thumbColor: _C.white,
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
    final text = data['text']?.toString() ?? '';
    final status = data['status']?.toString() ?? 'sent';
    final isUnread = isReceived && status == 'sent';

    final snapshotKey =
        isReceived ? 'fromUserProfileSnapshot' : 'toUserProfileSnapshot';
    final snapshot = data[snapshotKey] is Map
        ? Map<String, dynamic>.from(data[snapshotKey] as Map)
        : <String, dynamic>{};

    final nickname = snapshot['nickname']?.toString() ?? '';
    final avatarUrl = snapshot['profileImageUrl']?.toString() ?? '';
    final university = snapshot['universityName']?.toString() ?? '';

    final createdAt = data['createdAt'];
    final timeText = _formatTime(createdAt);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => _showDetail(context, text, isUnread),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isUnread ? _C.pink50 : _C.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isUnread
                ? _C.primary.withValues(alpha: 0.15)
                : _C.gray200.withValues(alpha: 0.6),
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
            _Avatar(url: avatarUrl),
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
                            fontWeight:
                                isUnread ? FontWeight.w700 : FontWeight.w600,
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
                      fontWeight:
                          isUnread ? FontWeight.w500 : FontWeight.w400,
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
      askService.markAsRead(askId).catchError(
        (e) => debugPrint('[AskInbox] markAsRead failed: $e'),
      );
    }

    showCupertinoModalPopup(
      context: context,
      builder: (ctx) => _AskDetailSheet(
        data: data,
        isReceived: isReceived,
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

  const _Avatar({required this.url});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48,
      height: 48,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: _C.gray100,
        border: Border.all(color: _C.gray200.withValues(alpha: 0.5)),
      ),
      clipBehavior: Clip.antiAlias,
      child: CaptureProtectedImage(
        imageUrl: url,
        fit: BoxFit.cover,
        shape: CaptureProtectedImageShape.circle,
        backgroundColor: _C.gray100,
        placeholderIconColor: _C.gray300,
        placeholderIconSize: 24,
      ),
    );
  }
}

// =============================================================================
// 무물 상세 시트
// =============================================================================
class _AskDetailSheet extends StatelessWidget {
  final Map<String, dynamic> data;
  final bool isReceived;

  const _AskDetailSheet({
    required this.data,
    required this.isReceived,
  });

  @override
  Widget build(BuildContext context) {
    final text = data['text']?.toString() ?? '';
    final snapshotKey =
        isReceived ? 'fromUserProfileSnapshot' : 'toUserProfileSnapshot';
    final snapshot = data[snapshotKey] is Map
        ? Map<String, dynamic>.from(data[snapshotKey] as Map)
        : <String, dynamic>{};

    final nickname = snapshot['nickname']?.toString() ?? '사용자';
    final avatarUrl = snapshot['profileImageUrl']?.toString() ?? '';
    final university = snapshot['universityName']?.toString() ?? '';

    final label = isReceived ? '$nickname님의 질문' : '$nickname님에게 보낸 질문';

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.6,
      ),
      decoration: const BoxDecoration(
        color: _C.white,
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
              _Avatar(url: avatarUrl),
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
              color: _C.pink50,
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
              child: Icon(icon, size: 32, color: _C.primary.withValues(alpha: 0.5)),
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
