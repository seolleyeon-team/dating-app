import 'package:flutter/cupertino.dart';
import '../../features/matching/screens/mystery_card_screen.dart';
import '../../features/chat/screens/premium_chat_list_screen.dart';
import '../../features/event/screens/event_screen.dart';
import '../../features/community/screens/community_screen.dart';
import '../../features/profile/screens/my_page_screen.dart';
import '../../router/route_names.dart';
import 'main_scaffold_args.dart';

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

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.pendingRouteName != null) {
        Navigator.of(context, rootNavigator: true).pushNamed(
          widget.pendingRouteName!,
          arguments: widget.pendingRouteArgs,
        );
      }
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
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
              builder: (context) =>
                  MysteryCardScreen(onNavTap: (i) => _tabController.index = i),
            );
          case 1:
            return CupertinoTabView(
              builder: (context) =>
                  ChatListScreen(onNavTap: (i) => _tabController.index = i),
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
              builder: (context) =>
                  MysteryCardScreen(onNavTap: (i) => _tabController.index = i),
            );
        }
      },
    );
  }
}
