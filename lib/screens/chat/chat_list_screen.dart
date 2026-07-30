import 'package:flutter/material.dart';

import '../../shared/utils/legacy_stub_policy.dart';

/// Legacy Material stub — not used by production named routes.
class ChatListScreen extends StatelessWidget {
  const ChatListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (!LegacyStubPolicy.allowLegacyStubScreens) {
      LegacyStubPolicy.denyInRelease('screens.chat.ChatListScreen');
    }
    return Scaffold(
      appBar: AppBar(title: const Text('채팅 (legacy stub)')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            '이 화면은 미사용 스텁입니다.\n'
            '실사용 채팅은 lib/features/chat 경로를 사용하세요.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
