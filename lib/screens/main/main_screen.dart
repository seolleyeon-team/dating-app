import 'package:flutter/material.dart';
import '../matching/matching_screen.dart';
import '../chat/chat_list_screen.dart';
import '../event/event_screen.dart';
import '../community/community_screen.dart';
import '../profile/profile_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const MatchingScreen(),
    const ChatListScreen(),
    const EventScreen(),
    const CommunityScreen(),
    const ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: _screens),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.favorite), label: '설레연'),
          BottomNavigationBarItem(icon: Icon(Icons.chat), label: '채팅'),
          BottomNavigationBarItem(icon: Icon(Icons.event), label: '이벤트'),
          BottomNavigationBarItem(icon: Icon(Icons.forest), label: '대나무숲'),
          BottomNavigationBarItem(icon: Icon(Icons.person), label: '내 페이지'),
        ],
      ),
    );
  }
}
