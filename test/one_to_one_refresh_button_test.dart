import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/screens/mystery_card_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  testWidgets('refresh button sits in the header next to the asks inbox icon', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const CupertinoApp(home: MysteryCardScreen(heartBalance: 20)),
    );
    await tester.pumpAndSettle();

    final refreshFinder = find.byKey(const Key('one_to_one_refresh_button'));
    final asksInboxFinder = find.byIcon(CupertinoIcons.tray_fill);
    expect(refreshFinder, findsOneWidget);
    expect(asksInboxFinder, findsOneWidget);

    // 무물함 아이콘의 바로 왼쪽 배치: 같은 헤더 Row 에서 refresh 가 왼쪽.
    final refreshX = tester.getCenter(refreshFinder).dx;
    final asksX = tester.getCenter(asksInboxFinder).dx;
    expect(refreshX, lessThan(asksX));
    expect(find.byKey(const Key('main_heart_balance')), findsOneWidget);
    expect(find.text('20'), findsOneWidget);

    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'tapping refresh without a loaded recommendation set shows guidance, '
    'never a payment CTA',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(const CupertinoApp(home: MysteryCardScreen()));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('one_to_one_refresh_button')));
      await tester.pumpAndSettle();

      expect(find.textContaining('새로고침할 추천을 준비하지 못했어요'), findsOneWidget);
      // 결제 확인 문구/CTA 는 열리지 않아야 한다.
      expect(find.text('정말로 새로고침 하시겠습니까?'), findsNothing);
      expect(find.text('새로고침 하기'), findsNothing);

      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
}
