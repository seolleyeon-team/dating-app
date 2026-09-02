import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('tutorial copy and sequence match the revised product flow', () {
    final today = File(
      'lib/features/tutorial/screens/todays_match_tutorial_screen.dart',
    ).readAsStringSync();
    final promise = File(
      'lib/features/tutorial/screens/promise_agreement_tutorial_screen.dart',
    ).readAsStringSync();
    final safety = File(
      'lib/features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart',
    ).readAsStringSync();
    final router = File('lib/router/app_router.dart').readAsStringSync();

    expect(today, contains('하트를 사용하여'));
    expect(today, isNot(contains('재화를 사용하여')));
    expect(
      promise,
      contains('pushNamed(RouteNames.bambooForestWriteTutorial)'),
    );
    expect(safety, isNot(contains('3:3 미팅 매너 보증금 제도')));
    expect(safety, contains('투명한 얼굴 공개'));
    expect(safety, contains('존중하는 매너'));
    expect(router, isNot(contains('SlotMachineTutorialScreen')));
    expect(router, isNot(contains('SeasonMeetingIntroScreen')));
  });

  test(
    'profile edit uses consistent labels and hides obsolete affordances',
    () {
      final options = File(
        'lib/constants/profile_options.dart',
      ).readAsStringSync();
      final edit = File(
        'lib/features/profile/screens/profile_edit_screen.dart',
      ).readAsStringSync();

      expect(options, contains("ProfileOption('friend', '가볍게 알아가고 싶어요')"));
      expect(edit, isNot(contains(RegExp(r"'\+\d+%'"))));
      expect(edit, isNot(contains('사진 가이드 참고하기')));
      expect(edit, isNot(contains('자기소개 꿀팁')));
      expect(edit, contains('showAddIcon: index != 0'));
      expect(RegExp(r'MbtiChoiceGrid\(').allMatches(edit).length, 2);
    },
  );

  test('profile detail exposes the newly required grouped information', () {
    final detail = File(
      'lib/features/matching/screens/profile_specific_detail_screen.dart',
    ).readAsStringSync();

    expect(detail, contains("_SectionTitle(text: '학교 정보')"));
    expect(detail, contains("_InfoChip(label: '학년'"));
    expect(detail, contains("_InfoChip(label: '학과'"));
    expect(detail, contains("label: 'RA 여부'"));
    expect(detail, contains("_SectionTitle(text: '나를 소개하는 키워드')"));
    expect(detail, contains("label: '내가 찾는 관계'"));
    expect(detail, isNot(contains("label: '연애관'")));
    expect(detail, contains('profileRelationshipOptions'));
  });

  test(
    'promise place categories are laid out below an opaque navigation bar',
    () {
      final picker = File(
        'lib/features/chat/widgets/promise_place_picker_sheet.dart',
      ).readAsStringSync();

      expect(
        picker,
        contains('backgroundColor: CupertinoColors.systemBackground,'),
      );
      expect(picker, isNot(contains('const SizedBox(height: 44)')));
      expect(picker, contains("label: '전체'"));
      expect(picker, contains("label: '그 외 장소'"));
    },
  );
}
