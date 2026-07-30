import 'package:flutter/cupertino.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/auth/screens/kakao_auth_main_screen.dart';
import 'package:seolleyeon/shared/widgets/seolleyeon_bottom_navigation_bar.dart';

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  group('accessibility semantics', () {
    testWidgets('bottom nav tabs expose button semantics labels', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(
        const CupertinoApp(
          home: SeolleyeonBottomNavigationBar(
            currentTab: BottomNavTab.matching,
            showChatBadge: true,
          ),
        ),
      );

      expect(find.bySemanticsLabel('설레연'), findsOneWidget);
      expect(find.bySemanticsLabel('채팅, 새 메시지'), findsOneWidget);

      final matchingSemantics = tester.getSemantics(
        find.bySemanticsLabel('설레연'),
      );
      expect(matchingSemantics.hasFlag(SemanticsFlag.isButton), isTrue);
      expect(matchingSemantics.hasFlag(SemanticsFlag.isSelected), isTrue);
    });

    testWidgets('kakao auth main screen exposes primary action semantics', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(
        CupertinoApp(home: KakaoAuthMainScreen(onKakaoLogin: () {})),
      );

      expect(find.bySemanticsLabel('카카오로 계속하기'), findsOneWidget);
      expect(find.bySemanticsLabel('뒤로 가기'), findsOneWidget);

      final loginSemantics = tester.getSemantics(
        find.bySemanticsLabel('카카오로 계속하기'),
      );
      expect(loginSemantics.hasFlag(SemanticsFlag.isButton), isTrue);
    });
  });
}
