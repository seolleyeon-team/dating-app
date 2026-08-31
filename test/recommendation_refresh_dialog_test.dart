import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/services/recommendation_refresh_service.dart';
import 'package:seolleyeon/features/matching/widgets/recommendation_refresh_dialog.dart';

Future<void> pumpDialog(
  WidgetTester tester,
  Future<RecommendationRefreshPurchaseResult> Function() onPurchase, {
  void Function(RecommendationRefreshPurchaseResult?)? onClosed,
}) async {
  await tester.pumpWidget(
    CupertinoApp(
      home: Builder(
        builder: (context) => Center(
          child: CupertinoButton(
            onPressed: () async {
              final result =
                  await showCupertinoDialog<
                    RecommendationRefreshPurchaseResult
                  >(
                    context: context,
                    builder: (_) =>
                        RecommendationRefreshDialog(onPurchase: onPurchase),
                  );
              onClosed?.call(result);
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('confirmation dialog shows the required copy and 5-heart price', (
    tester,
  ) async {
    await pumpDialog(
      tester,
      () async => const RecommendationRefreshPurchaseResult(
        status: RecommendationRefreshStatus.purchased,
      ),
    );

    expect(find.text('정말로 새로고침 하시겠습니까?'), findsOneWidget);
    expect(find.text('새로고침 하기'), findsOneWidget);
    expect(find.text('5 하트'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.heart_fill), findsOneWidget);
    expect(find.text('취소'), findsOneWidget);
  });

  testWidgets('CTA disables while the purchase is in flight and pops with the '
      'server result', (tester) async {
    final completer = Completer<RecommendationRefreshPurchaseResult>();
    var purchaseCalls = 0;
    RecommendationRefreshPurchaseResult? closedWith;
    await pumpDialog(tester, () {
      purchaseCalls++;
      return completer.future;
    }, onClosed: (result) => closedWith = result);

    await tester.tap(
      find.byKey(const Key('one_to_one_refresh_confirm_button')),
    );
    await tester.pump();

    // Loading state: spinner visible, CTA/cancel no longer tappable.
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    await tester.tap(
      find.byKey(const Key('one_to_one_refresh_confirm_button')),
    );
    await tester.pump();
    expect(purchaseCalls, 1);

    completer.complete(
      const RecommendationRefreshPurchaseResult(
        status: RecommendationRefreshStatus.purchased,
        remainingHearts: 7,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('정말로 새로고침 하시겠습니까?'), findsNothing);
    expect(closedWith?.status, RecommendationRefreshStatus.purchased);
    expect(closedWith?.remainingHearts, 7);
  });

  testWidgets('a thrown purchase error keeps the dialog open for retry', (
    tester,
  ) async {
    var purchaseCalls = 0;
    await pumpDialog(tester, () async {
      purchaseCalls++;
      throw StateError('network');
    });

    await tester.tap(
      find.byKey(const Key('one_to_one_refresh_confirm_button')),
    );
    await tester.pumpAndSettle();

    expect(find.text('정말로 새로고침 하시겠습니까?'), findsOneWidget);
    expect(find.textContaining('새로고침을 완료하지 못했어요'), findsOneWidget);

    await tester.tap(
      find.byKey(const Key('one_to_one_refresh_confirm_button')),
    );
    await tester.pumpAndSettle();
    expect(purchaseCalls, 2);
  });
}
