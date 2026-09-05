import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import '../../features/matching/screens/mystery_card_screen.dart';
import '../../features/chat/screens/premium_chat_list_screen.dart';
import '../../features/event/screens/event_screen.dart';
import '../../features/community/screens/community_screen.dart';
import '../../features/profile/screens/my_page_screen.dart';
import '../widgets/sensitive_screen_protection.dart';
import '../../providers/auth_provider.dart';
import '../../services/push_notification_service.dart';
import '../utils/privacy_log_utils.dart';

/// 메인 화면 스캐폴드 (CupertinoTabScaffold, 5탭: 설레연/채팅/이벤트/대나무숲/내 페이지)
class MainScaffold extends StatefulWidget {
  final int initialTabIndex;
  final String? pendingRouteName;
  final Object? pendingRouteArgs;

  const MainScaffold({
    super.key,
    this.initialTabIndex = 0,
    this.pendingRouteName,
    this.pendingRouteArgs,
  });

  @override
  State<MainScaffold> createState() => _MainScaffoldState();
}

class _MainScaffoldState extends State<MainScaffold> {
  late final CupertinoTabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = CupertinoTabController(
      initialIndex: widget.initialTabIndex,
    );
    _tabController.addListener(_syncChatListVisibility);
    _syncChatListVisibility();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.pendingRouteName != null) {
        Navigator.of(context, rootNavigator: true).pushNamed(
          widget.pendingRouteName!,
          arguments: widget.pendingRouteArgs,
        );
      }
      _resumePendingShareInvite();
    });
  }

  /// A share link (Kakao "친구 추가하기", App Link) opened on a cold start is
  /// parsed before this shell exists, and the splash → main route reset can
  /// close its confirmation. Re-present it here. This only routes to the
  /// confirmation step; nothing is accepted without the user's tap.
  void _resumePendingShareInvite() {
    if (!mounted) return;
    try {
      final auth = context.read<AuthProvider>();
      unawaited(auth.resumePendingInvite());
    } catch (e) {
      // No AuthProvider above this scaffold (tests / previews).
      debugPrint(
        '[MainScaffold] invite resume skipped: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  @override
  void dispose() {
    _tabController.removeListener(_syncChatListVisibility);
    PushNotificationService.instance.setChatListVisible(false);
    _tabController.dispose();
    super.dispose();
  }

  void _syncChatListVisibility() {
    PushNotificationService.instance.setChatListVisible(
      _tabController.index == 1,
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoTabScaffold(
      controller: _tabController,
      tabBar: CupertinoTabBar(
        height: 0,
        backgroundColor: const Color(0x00000000),
        border: const Border(),
        items: const [
          BottomNavigationBarItem(icon: SizedBox.shrink(), label: ''),
          BottomNavigationBarItem(icon: SizedBox.shrink(), label: ''),
          BottomNavigationBarItem(icon: SizedBox.shrink(), label: ''),
          BottomNavigationBarItem(icon: SizedBox.shrink(), label: ''),
          BottomNavigationBarItem(icon: SizedBox.shrink(), label: ''),
        ],
      ),
      tabBuilder: (context, index) {
        switch (index) {
          case 0:
            return CupertinoTabView(
              builder: (context) => SensitiveScreenProtection(
                child: MysteryCardScreen(
                  onNavTap: (i) => _tabController.index = i,
                ),
              ),
            );
          case 1:
            return CupertinoTabView(
              builder: (context) => SensitiveScreenProtection(
                child: ChatListScreen(
                  onNavTap: (i) => _tabController.index = i,
                ),
              ),
            );
          case 2:
            return CupertinoTabView(
              builder: (context) =>
                  EventScreen(onNavTap: (i) => _tabController.index = i),
            );
          case 3:
            return CupertinoTabView(
              builder: (context) =>
                  CommunityScreen(onNavTap: (i) => _tabController.index = i),
            );
          case 4:
            return CupertinoTabView(
              builder: (context) =>
                  MyPageScreen(onNavTap: (i) => _tabController.index = i),
            );
          default:
            return CupertinoTabView(
              builder: (context) => SensitiveScreenProtection(
                child: MysteryCardScreen(
                  onNavTap: (i) => _tabController.index = i,
                ),
              ),
            );
        }
      },
    );
  }
}
