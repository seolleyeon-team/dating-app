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

  testWidgets('recommendation screen shows loading then signed-out state', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const CupertinoApp(home: MysteryCardScreen()));
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(find.text('추천 준비 중'), findsNothing);
    expect(tester.takeException(), isNull);

    await tester.pumpAndSettle();
    expect(find.text('로그인이 필요해요.'), findsOneWidget);
    expect(find.byKey(const Key('locker_recommendation_board')), findsNothing);
    expect(find.textContaining('새로고침 ·'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
