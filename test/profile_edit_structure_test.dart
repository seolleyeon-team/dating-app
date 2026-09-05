import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/profile/screens/profile_edit_screen.dart';
import 'package:seolleyeon/shared/widgets/mbti_choice_grid.dart';
import 'package:seolleyeon/shared/widgets/profile_photo_mosaic.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(_loadFonts);

  testWidgets('locks profile-edit section geometry and scroll anchors', (
    tester,
  ) async {
    await _pumpProfileEdit(tester);

    final mosaic = find.byType(ProfilePhotoMosaic);
    expect(tester.getSize(mosaic), const Size(318, 318));

    final slotSizes = find
        .descendant(of: mosaic, matching: find.byType(SizedBox))
        .evaluate()
        .map((element) => tester.getSize(find.byWidget(element.widget)))
        .where((size) => size.width >= 90 && size.height >= 90)
        .toList();
    expect(
      slotSizes.where((size) => _closeSize(size, const Size(209.333, 209.333))),
      hasLength(1),
    );
    expect(
      slotSizes.where((size) => _closeSize(size, const Size(100.667, 100.667))),
      hasLength(5),
    );

    expect(find.text('자기소개 꿀팁'), findsOneWidget);
    final sectionTitles = [
      '프로필 사진',
      '자기소개',
      '프로필 문답',
      '닉네임',
      'MBTI',
      '키워드',
      '이상형 키워드',
      '라이프스타일',
      '이상형 키',
      '이상형 나이대',
      '이상형 MBTI',
      '이상형 계열',
      '이상형 라이프스타일',
    ];
    final sectionOffsets = sectionTitles
        .map((title) => tester.getTopLeft(find.text(title).first).dy)
        .toList();
    for (var index = 1; index < sectionOffsets.length; index++) {
      expect(
        sectionOffsets[index],
        greaterThan(sectionOffsets[index - 1]),
        reason:
            '${sectionTitles[index]} must follow ${sectionTitles[index - 1]}',
      );
    }

    final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
    expect(scrollable.position.pixels, 0);
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(0, -620),
    );
    await tester.pumpAndSettle();
    expect(scrollable.position.pixels, closeTo(600, 0.01));
  });

  testWidgets('locks MBTI sheet geometry, selection, and background anchor', (
    tester,
  ) async {
    await _pumpProfileEdit(tester);

    await tester.ensureVisible(find.text('MBTI').first);
    await tester.pumpAndSettle();
    final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
    final backgroundAnchor = scrollable.position.pixels;

    await tester.tap(find.text('MBTI').first);
    await tester.pumpAndSettle();

    expect(scrollable.position.pixels, backgroundAnchor);
    final surfaceRect = tester.getRect(find.byType(CupertinoPopupSurface));
    expect(surfaceRect.width, 360);
    expect(surfaceRect.center.dx, 195);
    expect(surfaceRect.height, lessThanOrEqualTo(844 * 0.75));

    final grid = find.byType(MbtiChoiceGrid);
    expect(grid, findsOneWidget);
    final gridRect = tester.getRect(grid);
    expect(gridRect.left, surfaceRect.left);
    expect(gridRect.right, surfaceRect.right);
    expect(gridRect.top, greaterThan(surfaceRect.top));
    expect(gridRect.bottom, surfaceRect.bottom);

    final buttons = find
        .descendant(of: grid, matching: find.byType(AnimatedContainer))
        .evaluate()
        .map((element) => tester.getSize(find.byWidget(element.widget)))
        .toList();
    expect(buttons, hasLength(8));
    for (final size in buttons) {
      expect(size.height, 70);
      expect(size.width, closeTo(71, 0.01));
    }

    for (final letter in ['I', 'S', 'T', 'P']) {
      await tester.tap(find.text(letter));
      await tester.pumpAndSettle();
    }
    expect(tester.widget<MbtiChoiceGrid>(grid).selectedValue, 'ISTP');

    await tester.tap(find.text('완료'));
    await tester.pumpAndSettle();
    expect(find.text('ISTP'), findsOneWidget);
  });
}

bool _closeSize(Size actual, Size expected) =>
    (actual.width - expected.width).abs() < 0.01 &&
    (actual.height - expected.height).abs() < 0.01;

Future<void> _loadFonts() async {
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
}

Future<void> _pumpProfileEdit(WidgetTester tester) async {
  tester.view.devicePixelRatio = 3;
  tester.view.physicalSize = const Size(1170, 2532);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);

  await tester.pumpWidget(
    const CupertinoApp(
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
  );
  await tester.pumpAndSettle();
}
