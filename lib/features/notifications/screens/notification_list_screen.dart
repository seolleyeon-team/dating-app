import 'package:flutter/cupertino.dart';

import '../../../router/route_names.dart';
import '../../../services/storage_service.dart';
import '../../../shared/layouts/main_scaffold_args.dart';
import '../models/app_notification.dart';
import '../services/notification_service.dart';

class _AppColors {
  static const Color primary = Color(0xFFFF5A7E);
  static const Color textMain = Color(0xFF111111);
  static const Color textSub = Color(0xFF6B7280);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color unreadBg = Color(0xFFFFF5F7);
}

class NotificationListScreen extends StatefulWidget {
  const NotificationListScreen({super.key});

  @override
  State<NotificationListScreen> createState() => _NotificationListScreenState();
}

class _NotificationListScreenState extends State<NotificationListScreen> {
  final StorageService _storageService = StorageService();
  final NotificationService _notificationService = NotificationService();

  String? _currentUserId;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final userId = await _storageService.getKakaoUserId();

    if (!mounted) return;
    setState(() {
      _currentUserId = userId;
      _isLoading = false;
    });
  }

  Future<void> _openNotification(AppNotification notification) async {
    final userId = _currentUserId;
    if (userId == null || userId.isEmpty) return;

    if (!notification.isRead) {
      await _notificationService.markAsRead(
        userId: userId,
        notificationId: notification.id,
      );
    }

    if (!mounted) return;

    final deeplinkType = notification.deeplinkType ?? '';
    final deeplinkId = notification.deeplinkId ?? '';

    if (deeplinkType == 'chat') {
      Navigator.of(context, rootNavigator: true).pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 1),
      );
      return;
    }

    if (deeplinkType == 'community_post') {
      Navigator.of(context, rootNavigator: true).pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: MainScaffoldArgs(
          initialTabIndex: 3,
          pendingRouteName: RouteNames.postDetail,
          pendingRouteArgs: notification.postId ?? deeplinkId,
        ),
      );
      return;
    }

    if (deeplinkType == 'received_like') {
      Navigator.of(context, rootNavigator: true).pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 4),
      );
      Future.delayed(const Duration(milliseconds: 300), () {
        if (!mounted) return;
        Navigator.of(context, rootNavigator: true)
            .pushNamed(RouteNames.receivedHearts);
      });
      return;
    }

    if (deeplinkType == 'asks_inbox') {
      Navigator.of(context, rootNavigator: true).pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 4),
      );
      Future.delayed(const Duration(milliseconds: 300), () {
        if (!mounted) return;
        Navigator.of(context, rootNavigator: true)
            .pushNamed(RouteNames.asksInbox);
      });
      return;
    }
  }

  Future<void> _markAllAsRead() async {
    final userId = _currentUserId;
    if (userId == null || userId.isEmpty) return;
    await _notificationService.markAllAsRead(userId);
  }

  String _formatTime(DateTime dateTime) {
    final now = DateTime.now();
    final diff = now.difference(dateTime);

    if (diff.inMinutes < 1) return '방금 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';

    return '${dateTime.month}/${dateTime.day}';
  }

  IconData _iconForType(String type) {
    switch (type) {
      case 'chat_digest':
        return CupertinoIcons.chat_bubble_2_fill;
      case 'community_post_like':
        return CupertinoIcons.heart_fill;
      case 'community_comment':
        return CupertinoIcons.text_bubble_fill;
      case 'community_reply':
        return CupertinoIcons.arrowshape_turn_up_left_fill;
      case 'profile_like':
        return CupertinoIcons.person_crop_circle;
      case 'ask_received':
        return CupertinoIcons.question_circle_fill;
      default:
        return CupertinoIcons.bell_fill;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const CupertinoPageScaffold(
        child: Center(child: CupertinoActivityIndicator()),
      );
    }

    final userId = _currentUserId;
    if (userId == null || userId.isEmpty) {
      return CupertinoPageScaffold(
        navigationBar: CupertinoNavigationBar(
          middle: const Text('알림'),
          leading: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () => Navigator.of(context).maybePop(),
            child: const Icon(CupertinoIcons.back),
          ),
        ),
        child: const SafeArea(
          child: Center(
            child: Text(
              '로그인 정보가 없어요',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                color: _AppColors.textSub,
              ),
            ),
          ),
        ),
      );
    }

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: CupertinoColors.systemBackground.withValues(
          alpha: 0.96,
        ),
        border: const Border(
          bottom: BorderSide(color: _AppColors.gray200, width: 0.6),
        ),
        middle: const Text('알림', style: TextStyle(fontFamily: 'Pretendard')),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).maybePop(),
          child: const Icon(CupertinoIcons.back),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _markAllAsRead,
          child: const Text(
            '모두 읽음',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: _AppColors.primary,
            ),
          ),
        ),
      ),
      child: SafeArea(
        top: true,
        child: StreamBuilder<List<AppNotification>>(
          stream: _notificationService.notificationsStream(userId),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting &&
                !snapshot.hasData) {
              return const Center(child: CupertinoActivityIndicator());
            }

            if (snapshot.hasError) {
              return Center(
                child: Text(
                  '알림을 불러오지 못했어요\n${snapshot.error}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    color: _AppColors.textSub,
                  ),
                ),
              );
            }

            final notifications = snapshot.data ?? const <AppNotification>[];
            final unreadCount = notifications.where((e) => !e.isRead).length;

            return CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: CupertinoColors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: _AppColors.gray200),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '새 알림',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.textSub,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            unreadCount > 0
                                ? '읽지 않은 알림이 $unreadCount개 있어요'
                                : '모든 알림을 확인했어요',
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 17,
                              fontWeight: FontWeight.w800,
                              color: _AppColors.textMain,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(20, 10, 20, 8),
                    child: Text(
                      '최근 알림',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ),
                ),
                if (notifications.isEmpty)
                  const SliverFillRemaining(
                    hasScrollBody: false,
                    child: Center(
                      child: Text(
                        '아직 알림이 없어요',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          color: _AppColors.textSub,
                        ),
                      ),
                    ),
                  )
                else
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                    sliver: SliverList.separated(
                      itemCount: notifications.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 10),
                      itemBuilder: (context, index) {
                        final notification = notifications[index];

                        return CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () => _openNotification(notification),
                          child: Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: notification.isRead
                                  ? CupertinoColors.white
                                  : _AppColors.unreadBg,
                              borderRadius: BorderRadius.circular(18),
                              border: Border.all(color: _AppColors.gray200),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Container(
                                  width: 42,
                                  height: 42,
                                  decoration: BoxDecoration(
                                    color: _AppColors.gray100,
                                    shape: BoxShape.circle,
                                  ),
                                  child: Icon(
                                    _iconForType(notification.type),
                                    size: 20,
                                    color: _AppColors.primary,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Expanded(
                                            child: Text(
                                              notification.title,
                                              style: TextStyle(
                                                fontFamily: 'Pretendard',
                                                fontSize: 14,
                                                fontWeight: notification.isRead
                                                    ? FontWeight.w600
                                                    : FontWeight.w800,
                                                color: _AppColors.textMain,
                                              ),
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Text(
                                            _formatTime(notification.createdAt),
                                            style: const TextStyle(
                                              fontFamily: 'Pretendard',
                                              fontSize: 11,
                                              color: _AppColors.textSub,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 6),
                                      Text(
                                        notification.body,
                                        style: const TextStyle(
                                          fontFamily: 'Pretendard',
                                          fontSize: 13,
                                          height: 1.45,
                                          color: _AppColors.textSub,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                if (!notification.isRead) ...[
                                  const SizedBox(width: 8),
                                  Container(
                                    width: 8,
                                    height: 8,
                                    margin: const EdgeInsets.only(top: 6),
                                    decoration: const BoxDecoration(
                                      color: _AppColors.primary,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}
