import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/auth/screens/kakao_friend_connection_screen.dart';
import 'package:seolleyeon/shared/widgets/seolleyeon_bottom_navigation_bar.dart';

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

bool _semanticsFlagEnabled(Object? value) {
  if (value == true) return true;
  final text = value.toString();
  return text == 'true' || text == 'Tristate.isTrue';
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
      expect(
        _semanticsFlagEnabled(matchingSemantics.flagsCollection.isButton),
        isTrue,
      );
      expect(
        _semanticsFlagEnabled(matchingSemantics.flagsCollection.isSelected),
        isTrue,
      );
    });

    testWidgets(
      'kakao friend connection view exposes primary action semantics',
      (tester) async {
        await _useMobileSurface(tester);
        await tester.pumpWidget(
          CupertinoApp(
            home: KakaoFriendConnectionView(
              isConnecting: false,
              consentRefused: false,
              errorMessage: null,
              onConnectPressed: () {},
            ),
          ),
        );

        expect(find.bySemanticsLabel('카카오 친구 연결하기'), findsOneWidget);

        final connectSemantics = tester.getSemantics(
          find.bySemanticsLabel('카카오 친구 연결하기'),
        );
        expect(
          _semanticsFlagEnabled(connectSemantics.flagsCollection.isButton),
          isTrue,
        );
      },
    );
  });
}
