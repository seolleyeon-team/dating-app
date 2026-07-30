import 'package:flutter/material.dart';

import '../../shared/utils/legacy_stub_policy.dart';

/// Legacy Material stub — not used by production named routes.
class EventScreen extends StatelessWidget {
  const EventScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (!LegacyStubPolicy.allowLegacyStubScreens) {
      LegacyStubPolicy.denyInRelease('screens.event.EventScreen');
    }
    return Scaffold(
      appBar: AppBar(title: const Text('이벤트 (legacy stub)')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            '이 화면은 미사용 스텁입니다.\n'
            '실사용 이벤트는 lib/features/event 경로를 사용하세요.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
