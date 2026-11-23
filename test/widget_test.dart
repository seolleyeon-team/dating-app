// 설레연 앱 기본 위젯 테스트

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/app.dart';
import 'package:seolleyeon/services/push_notification_service.dart';

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

    // AUD-16: 푸시 리스너는 이제 awaited setup 보다 먼저, 프로세스당 한 번
    // 붙는다. 그때 시작되는 45초 주기 delivery-context heartbeat 는 앱 수명
    // 동안 도는 타이머라 시간을 흘려서는 소진되지 않으므로, 서비스가 제공하는
    // 테스트용 정리 훅으로 내린다.
    PushNotificationService.instance.resetForTest();
  });
}
