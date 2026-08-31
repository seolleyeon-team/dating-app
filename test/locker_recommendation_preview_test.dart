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

  testWidgets('locker UI stays visible while recommendations are empty', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const CupertinoApp(home: MysteryCardScreen()));
    // 검증 대상은 "추천이 비어 있는 동안" 사물함이 계속 보이는지다.
    // pumpAndSettle 은 비동기 추천 로드를 끝까지 돌리는데, 위젯 테스트에는
    // 카카오 사용자 id 가 없어서 그 로드가 실패로 끝난다. 그러면 화면은
    // 재시도 분기(RecommendationLoadFailure)로 넘어가 버려서, 이름이 말하는
    // 상태에 도달하지 못한 채 실패한다.
    // pumpWidget 이 그린 첫 프레임이 정확히 "로딩/비어 있음" 상태다
    // (_isLoading == true, 로드 실패 플래그는 아직 false).
    // 여기서 한 번 더 pump 하면 완료된 로드의 setState 가 반영돼 상태가 바뀐다.
    expect(
      find.byKey(const Key('locker_recommendation_board')),
      findsOneWidget,
    );
    expect(find.text('추천 준비 중'), findsNWidgets(3));
    expect(tester.takeException(), isNull);

    // 남은 비동기 작업을 정리한다 (pending timer 로 테스트가 흔들리지 않도록).
    await tester.pumpAndSettle();
  });
}
