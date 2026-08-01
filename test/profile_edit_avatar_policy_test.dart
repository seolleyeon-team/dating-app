import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('profile edit keeps avatar media display-only', () {
    final source = File(
      'lib/features/profile/screens/profile_edit_screen.dart',
    ).readAsStringSync();

    expect(source, isNot(contains('ImagePicker')));
    expect(source, isNot(contains('uploadPickedImage(')));
    expect(source, isNot(contains('saveOnboardingPhotos(')));
    expect(source, contains('_showProfileAvatarDisplayOnlyDialog'));
    expect(source, contains('_showLockedAvatarDialog'));
    expect(source, contains('_showSourceLockedAvatarDialog'));
  });
}
