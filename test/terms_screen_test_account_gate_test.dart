import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/screens/terms_screen.dart';
import 'package:seolleyeon/shared/utils/dev_entry_policy.dart';

const _testAccountLabel = '테스트 계정으로 둘러보기';

Future<void> pumpTermsScreen(WidgetTester tester) async {
  await tester.pumpWidget(const CupertinoApp(home: TermsScreen()));
  await tester.pump();
}

void main() {
  tearDown(() => DevEntryPolicy.debugSetTestAccountEntry(null));

  testWidgets(
    'release builds do not offer an entry point that skips student verification',
    (tester) async {
      DevEntryPolicy.debugSetTestAccountEntry(false);

      await pumpTermsScreen(tester);

      // The button signed the user in as a hardcoded uid, skipping Kakao login
      // and Yonsei verification, and dropped them straight onto the main tab.
      expect(find.text(_testAccountLabel), findsNothing);
    },
  );

  testWidgets('debug builds keep the test account shortcut', (tester) async {
    DevEntryPolicy.debugSetTestAccountEntry(true);

    await pumpTermsScreen(tester);

    expect(find.text(_testAccountLabel), findsOneWidget);
  });

  test('the shortcut is off unless the build is a debug build', () {
    DevEntryPolicy.debugSetTestAccountEntry(null);

    expect(DevEntryPolicy.allowTestAccountEntry, kDebugMode);
  });
}
