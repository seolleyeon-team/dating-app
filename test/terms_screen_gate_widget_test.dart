import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/screens/terms_screen.dart';
import 'package:seolleyeon/shared/utils/dev_entry_policy.dart';

/// Behavioural cover for the terms gate's UI half (terms-gate contract §2/§7).
///
/// The screen is the only place the four REQUIRED documents are collected, so
/// the CTA enablement rule and the "전체 동의" symmetry (finding F4) are the
/// invariants that decide what the pending acceptance can contain.
void main() {
  const ctaLabel = '동의하고 시작하기';
  const allAgreeLabel = '전체 동의';

  setUp(() => DevEntryPolicy.debugSetTestAccountEntry(false));
  tearDown(() => DevEntryPolicy.debugSetTestAccountEntry(null));

  Future<void> pumpTermsScreen(WidgetTester tester) async {
    // The screen pins its CTA over the scroll area; a tall surface keeps the
    // optional switches out from under that overlay so taps reach them.
    await tester.binding.setSurfaceSize(const Size(420, 1600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const CupertinoApp(home: TermsScreen()));
    await tester.pumpAndSettle();
  }

  /// The CTA is a `CupertinoButton` whose `onPressed` is null while disabled.
  bool ctaEnabled(WidgetTester tester) {
    final button = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.text(ctaLabel),
        matching: find.byType(CupertinoButton),
      ),
    );
    return button.onPressed != null;
  }

  Finder switchAt(int index) => find.byType(CupertinoSwitch).at(index);

  bool switchValue(WidgetTester tester, int index) =>
      tester.widget<CupertinoSwitch>(switchAt(index)).value;

  /// The required-item labels live in a `RichText` span, so the finder must
  /// opt into rich text.
  Future<void> tapRequired(WidgetTester tester, String label) async {
    final finder = find.textContaining(label, findRichText: true);
    expect(finder, findsOneWidget, reason: 'required row: $label');
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  const requiredLabels = <String>[
    '서비스 이용약관 동의',
    '개인정보 처리방침 동의',
    '본인인증 정보 수집·이용 동의',
    '연 나이 20세 이상입니다',
  ];

  testWidgets('the CTA stays disabled while any REQUIRED item is unchecked', (
    tester,
  ) async {
    await pumpTermsScreen(tester);
    expect(ctaEnabled(tester), isFalse);

    // Three of four is still not enough.
    for (final label in requiredLabels.take(3)) {
      await tapRequired(tester, label);
      expect(ctaEnabled(tester), isFalse, reason: 'after $label');
    }
  });

  testWidgets('all four REQUIRED items with EVERY optional item off still '
      'lets the user proceed', (tester) async {
    await pumpTermsScreen(tester);

    for (final label in requiredLabels) {
      await tapRequired(tester, label);
    }

    // Contract §2: optional consents are never blocking.
    expect(switchValue(tester, 0), isFalse, reason: 'push stays off');
    expect(switchValue(tester, 1), isFalse, reason: 'email stays off');
    expect(ctaEnabled(tester), isTrue);
  });

  testWidgets('F4: 전체 동의 on→off clears the push and email switches', (
    tester,
  ) async {
    await pumpTermsScreen(tester);

    await tester.tap(find.text(allAgreeLabel));
    await tester.pumpAndSettle();
    expect(switchValue(tester, 0), isTrue);
    expect(switchValue(tester, 1), isTrue);
    expect(ctaEnabled(tester), isTrue);

    // The old asymmetric implementation left both switches stuck on.
    await tester.tap(find.text(allAgreeLabel));
    await tester.pumpAndSettle();
    expect(switchValue(tester, 0), isFalse);
    expect(switchValue(tester, 1), isFalse);
    expect(ctaEnabled(tester), isFalse);
  });

  testWidgets('an optional switch toggled on its own never opens the gate', (
    tester,
  ) async {
    await pumpTermsScreen(tester);

    await tester.tap(switchAt(0));
    await tester.pumpAndSettle();
    expect(switchValue(tester, 0), isTrue);
    expect(switchValue(tester, 1), isFalse);
    // Optional switches never gate the CTA.
    expect(ctaEnabled(tester), isFalse);
  });

  testWidgets('the detail sheet round-trips without losing checkbox state', (
    tester,
  ) async {
    await pumpTermsScreen(tester);

    // Check two required items, then open the first document's detail sheet.
    await tapRequired(tester, requiredLabels[1]);
    await tapRequired(tester, requiredLabels[2]);

    await tester.tap(find.text('보기').first);
    await tester.pumpAndSettle();
    expect(find.text('서비스 이용약관'), findsWidgets);

    // Agreeing inside the sheet checks that item and preserves the rest —
    // the sheet is a modal over the SAME screen state.
    await tester.tap(find.text('동의하기').last);
    await tester.pumpAndSettle();

    expect(ctaEnabled(tester), isFalse, reason: 'one required item remains');

    await tapRequired(tester, requiredLabels[3]);
    expect(ctaEnabled(tester), isTrue);
  });
}
