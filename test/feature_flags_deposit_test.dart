import 'package:flutter_test/flutter_test.dart';

import 'package:seolleyeon/core/feature_flags.dart';

void main() {
  test('season deposit feature flag defaults to fail-closed off', () {
    expect(kSeasonDepositEnabled, isFalse);
  });
}
