// 설레연 앱 기본 위젯 테스트

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/app.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  testWidgets('App launches successfully', (WidgetTester tester) async {
    // 앱 빌드 및 프레임 트리거
    await tester.pumpWidget(const SeolleyeonApp());

    // 앱이 정상적으로 로드되는지 확인
    expect(find.text('설레연'), findsWidgets);

    // SplashScreen과 AuthProvider의 지연 타이머가 테스트 종료 시점에 남지 않도록 소진한다.
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
  });
}
