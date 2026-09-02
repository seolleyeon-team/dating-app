import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/widgets/promise_place_picker_sheet.dart';
import 'package:seolleyeon/features/matching/screens/profile_specific_detail_screen.dart';
import 'package:seolleyeon/features/profile/screens/profile_edit_screen.dart';
import 'package:seolleyeon/features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart';
import 'package:seolleyeon/features/tutorial/screens/todays_match_tutorial_screen.dart';
import 'package:seolleyeon/shared/widgets/mbti_choice_grid.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await (FontLoader(
      'Pretendard',
    )..addFont(rootBundle.load('assets/fonts/PretendardVariable.ttf'))).load();
    await (FontLoader(
      'NanumSquareRound',
    )..addFont(rootBundle.load('assets/fonts/NanumSquareRoundR.ttf'))).load();
    await (FontLoader(
      'MaterialIcons',
    )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
    await (FontLoader('packages/cupertino_icons/CupertinoIcons')..addFont(
          rootBundle.load('packages/cupertino_icons/assets/CupertinoIcons.ttf'),
        ))
        .load();
  });

  void configurePhone(WidgetTester tester) {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1170, 2532);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
  }

  Future<void> pumpCaptureApp(
    WidgetTester tester, {
    required Key key,
    required Widget home,
  }) async {
    await tester.pumpWidget(
      RepaintBoundary(
        key: key,
        child: CupertinoApp(
          debugShowCheckedModeBanner: false,
          theme: const CupertinoThemeData(
            textTheme: CupertinoTextThemeData(
              textStyle: TextStyle(fontFamily: 'Pretendard'),
              actionTextStyle: TextStyle(fontFamily: 'Pretendard'),
              tabLabelTextStyle: TextStyle(fontFamily: 'Pretendard'),
              navTitleTextStyle: TextStyle(fontFamily: 'Pretendard'),
              navLargeTitleTextStyle: TextStyle(fontFamily: 'Pretendard'),
              navActionTextStyle: TextStyle(fontFamily: 'Pretendard'),
              pickerTextStyle: TextStyle(fontFamily: 'Pretendard'),
              dateTimePickerTextStyle: TextStyle(fontFamily: 'Pretendard'),
            ),
          ),
          home: home,
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 800));
  }

  testWidgets('captures revised daily recommendation tutorial', (tester) async {
    configurePhone(tester);
    const key = Key('daily-tutorial-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: TodaysMatchTutorialScreen(onStart: _noop, onSkip: _noop),
    );

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_01_daily_tutorial.png'),
    );
  });

  testWidgets('captures revised safety promises tutorial', (tester) async {
    configurePhone(tester);
    const key = Key('safety-tutorial-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const BambooForestSafetyTutorialScreen(),
    );

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_02_safety_promises.png'),
    );
  });

  testWidgets('captures profile photo and percentage cleanup', (tester) async {
    configurePhone(tester);
    const key = Key('profile-edit-top-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const ProfileEditScreen(showcase: true),
    );

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_03_profile_edit_top.png'),
    );
  });

  testWidgets('captures relationship and basic profile editing', (
    tester,
  ) async {
    configurePhone(tester);
    const key = Key('profile-edit-relationship-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const ProfileEditScreen(showcase: true),
    );
    final scroll = find.byType(SingleChildScrollView);
    await tester.drag(scroll, const Offset(0, -1150));
    await tester.pump(const Duration(milliseconds: 300));

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_04_profile_relationship.png'),
    );
  });

  testWidgets('captures ideal MBTI shared selector', (tester) async {
    configurePhone(tester);
    const key = Key('ideal-mbti-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const ProfileEditScreen(showcase: true),
    );
    final tile = find.text('이상형 MBTI');
    await tester.ensureVisible(tile);
    await tester.pumpAndSettle();
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(find.byType(MbtiChoiceGrid), findsOneWidget);

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_05_ideal_mbti.png'),
    );
  });

  testWidgets('captures profile detail school and keyword blocks', (
    tester,
  ) async {
    configurePhone(tester);
    const key = Key('profile-detail-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const ProfileDetailShowcaseScreen(),
    );
    final scroll = find.byType(SingleChildScrollView);
    await tester.drag(scroll, const Offset(0, -760));
    await tester.pump(const Duration(milliseconds: 300));

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_06_profile_detail.png'),
    );
  });

  testWidgets('captures unobstructed promise place categories', (tester) async {
    configurePhone(tester);
    const key = Key('promise-place-shot');
    await pumpCaptureApp(
      tester,
      key: key,
      home: const CupertinoPageScaffold(
        backgroundColor: Color(0xCC000000),
        child: PromisePlacePickerSheet(showcase: true),
      ),
    );

    await expectLater(
      find.byKey(key),
      matchesGoldenFile('goldens/requested_ui_07_promise_places.png'),
    );
  });
}

void _noop() {}
