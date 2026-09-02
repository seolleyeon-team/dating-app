import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/profile/screens/profile_edit_screen.dart';
import 'package:seolleyeon/shared/widgets/mbti_choice_grid.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await (FontLoader(
      'Pretendard',
    )..addFont(rootBundle.load('assets/fonts/PretendardVariable.ttf'))).load();
    await (FontLoader(
      'MaterialIcons',
    )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
    await (FontLoader('packages/cupertino_icons/CupertinoIcons')..addFont(
          rootBundle.load('packages/cupertino_icons/assets/CupertinoIcons.ttf'),
        ))
        .load();
  });

  testWidgets('captures every profile edit section on an iPhone-sized canvas', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1170, 2532);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    const showcaseKey = Key('profile-edit-showcase');
    await tester.pumpWidget(
      const RepaintBoundary(
        key: showcaseKey,
        child: CupertinoApp(
          debugShowCheckedModeBanner: false,
          theme: CupertinoThemeData(
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
          home: ProfileEditScreen(showcase: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final scrollView = find.byType(SingleChildScrollView);
    expect(scrollView, findsOneWidget);

    await expectLater(
      find.byKey(showcaseKey),
      matchesGoldenFile('goldens/profile_edit_showcase_01_top.png'),
    );

    for (var page = 2; page <= 6; page++) {
      await tester.drag(scrollView, const Offset(0, -620));
      await tester.pumpAndSettle();
      await expectLater(
        find.byKey(showcaseKey),
        matchesGoldenFile('goldens/profile_edit_showcase_0${page}_scroll.png'),
      );
    }
  });

  testWidgets('profile edit uses the onboarding MBTI selector', (tester) async {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1170, 2532);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    const showcaseKey = Key('profile-edit-mbti-showcase');
    await tester.pumpWidget(
      const RepaintBoundary(
        key: showcaseKey,
        child: CupertinoApp(
          debugShowCheckedModeBanner: false,
          theme: CupertinoThemeData(
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
          home: ProfileEditScreen(showcase: true),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('MBTI'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('MBTI'));
    await tester.pumpAndSettle();

    for (final letter in ['E', 'N', 'F', 'J', 'I', 'S', 'T', 'P']) {
      expect(find.text(letter), findsOneWidget);
    }

    for (final letter in ['I', 'S', 'T', 'P']) {
      await tester.tap(find.text(letter));
      await tester.pumpAndSettle();
    }

    await expectLater(
      find.byKey(showcaseKey),
      matchesGoldenFile('goldens/profile_edit_mbti_selector.png'),
    );

    await tester.tap(find.text('완료'));
    await tester.pumpAndSettle();
    expect(find.text('ISTP'), findsOneWidget);
  });

  testWidgets('ideal MBTI edit reuses the same MBTI choice grid', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1170, 2532);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const CupertinoApp(
        debugShowCheckedModeBanner: false,
        home: ProfileEditScreen(showcase: true),
      ),
    );
    await tester.pumpAndSettle();

    final idealMbtiTile = find.text('이상형 MBTI');
    await tester.ensureVisible(idealMbtiTile);
    await tester.pumpAndSettle();
    await tester.tap(idealMbtiTile);
    await tester.pumpAndSettle();

    expect(find.byType(MbtiChoiceGrid), findsOneWidget);
    for (final letter in ['E', 'N', 'F', 'J', 'I', 'S', 'T', 'P']) {
      expect(find.text(letter), findsOneWidget);
    }

    for (final letter in ['I', 'S', 'T', 'P']) {
      await tester.tap(find.text(letter));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('완료'));
    await tester.pumpAndSettle();

    expect(find.text('I, S, T, P'), findsOneWidget);
  });
}
