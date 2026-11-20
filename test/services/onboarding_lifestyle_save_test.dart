// 라이프스타일 저장은 고른 항목만 쓴다. 고르지 않은 항목을 null 로 쓰면
// 저장돼 있던 값이 지워진다.

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/onboarding_save_helper.dart';

void main() {
  test('아무것도 고르지 않았으면 쓸 필드가 없다 (기존 값을 덮지 않는다)', () {
    expect(
      OnboardingSaveHelper.selectedLifestyleFields(
        drinking: null,
        smoking: null,
        exercise: null,
        religion: null,
      ),
      isEmpty,
    );
  });

  test('고른 항목만 담고 나머지 키는 만들지 않는다', () {
    final fields = OnboardingSaveHelper.selectedLifestyleFields(
      drinking: 'sometimes',
      smoking: null,
      exercise: '',
      religion: null,
    );

    expect(fields, {'drinking': 'sometimes'});
    expect(fields.containsKey('smoking'), isFalse);
  });

  test('모두 고르면 네 항목이 그대로 저장된다', () {
    expect(
      OnboardingSaveHelper.selectedLifestyleFields(
        drinking: 'sometimes',
        smoking: 'nonSmoker',
        exercise: 'breathingOnly',
        religion: 'none',
      ),
      {
        'drinking': 'sometimes',
        'smoking': 'nonSmoker',
        'exercise': 'breathingOnly',
        'religion': 'none',
      },
    );
  });
}
