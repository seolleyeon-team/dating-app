import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/interest_taxonomy.dart';

void main() {
  test('일본 애니메이션은 드라마·영화 관심사로 등록되어 있다', () {
    final screenCategory = interestCategories.firstWhere(
      (category) => category.id == 'screen',
    );

    expect(screenCategory.title, '드라마, 영화');
    expect(screenCategory.items, contains('일본 애니메이션'));
    expect(interestCategoryIdOf('일본 애니메이션'), 'screen');
  });

  test('프로필 편집은 관심사를 전용 leaf write로 저장한다', () {
    final source = File(
      'lib/features/profile/screens/profile_edit_screen.dart',
    ).readAsStringSync();
    final saveStart = source.indexOf('Future<void> _saveProfile()');
    final nextMethod = source.indexOf('\n  Future<void> ', saveStart + 1);
    final saveSection = source.substring(
      saveStart,
      nextMethod == -1 ? source.length : nextMethod,
    );

    expect(saveSection, contains('saveOnboardingInterests'));
    expect(
      saveSection,
      contains('interests: List<String>.unmodifiable(_interests)'),
    );
    expect(saveSection, isNot(contains("'interests':")));
  });
}
