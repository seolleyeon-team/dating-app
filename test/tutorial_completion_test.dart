import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/tutorial/tutorial_completion.dart';
import 'package:seolleyeon/router/route_names.dart';

class _Harness {
  final pushed = <String>[];
  int marks = 0;
  Future<void> Function() onMark = () async {};

  Widget app() {
    return CupertinoApp(
      home: Builder(
        builder: (context) => Center(
          child: CupertinoButton(
            onPressed: () => completeTutorialAndEnterMain(
              context,
              markTutorialSeen: () {
                marks += 1;
                return onMark();
              },
            ),
            child: const Text('start'),
          ),
        ),
      ),
      onGenerateRoute: (settings) {
        pushed.add(settings.name ?? '');
        return CupertinoPageRoute<void>(
          settings: settings,
          builder: (_) => const Center(child: Text('main page')),
        );
      },
    );
  }
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

void main() {
  testWidgets('a second tap while the completion is being saved does not '
      'complete or enter the app again', (tester) async {
    final harness = _Harness();
    final gate = Completer<void>();
    harness.onMark = () => gate.future;
    await tester.pumpWidget(harness.app());

    await tester.tap(find.text('start'));
    await tester.pump();
    await tester.tap(find.text('start'));
    await tester.pump();

    expect(harness.marks, 1);
    expect(harness.pushed, isEmpty, reason: 'the marker is saved first');

    gate.complete();
    await _settle(tester);

    expect(harness.marks, 1);
    expect(harness.pushed, [RouteNames.main]);
    expect(find.text('main page'), findsOneWidget);
    expect(find.text('start'), findsNothing);
  });

  testWidgets('a failed save keeps the user in the tutorial and can be '
      'retried', (tester) async {
    final harness = _Harness();
    harness.onMark = () async {
      if (harness.marks == 1) throw StateError('permission-denied');
    };
    await tester.pumpWidget(harness.app());

    await tester.tap(find.text('start'));
    await _settle(tester);

    expect(find.text('완료 정보를 저장하지 못했어요'), findsOneWidget);
    expect(harness.pushed, isEmpty);

    await tester.tap(find.text('확인'));
    await _settle(tester);
    await tester.tap(find.text('start'));
    await _settle(tester);

    expect(harness.marks, 2);
    expect(harness.pushed, [RouteNames.main]);
  });

  testWidgets('a save that never finishes is reported instead of leaving a '
      'dead button', (tester) async {
    final harness = _Harness();
    harness.onMark = () => Completer<void>().future;
    await tester.pumpWidget(harness.app());

    await tester.tap(find.text('start'));
    await tester.pump(tutorialCompletionTimeout + const Duration(seconds: 1));
    await _settle(tester);

    expect(find.text('완료 정보를 저장하지 못했어요'), findsOneWidget);
    expect(harness.pushed, isEmpty);

    await tester.tap(find.text('확인'));
    await _settle(tester);
    await tester.tap(find.text('start'));
    await tester.pump();
    expect(harness.marks, 2);

    // Let the second attempt time out too so no timer outlives the test.
    await tester.pump(tutorialCompletionTimeout + const Duration(seconds: 1));
    await _settle(tester);
  });

  testWidgets('a completion that finishes after the tutorial is gone does '
      'not navigate', (tester) async {
    final harness = _Harness();
    final gate = Completer<void>();
    harness.onMark = () => gate.future;
    await tester.pumpWidget(harness.app());

    await tester.tap(find.text('start'));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    gate.complete();
    await _settle(tester);

    expect(tester.takeException(), isNull);
    expect(harness.pushed, isEmpty);

    // The guard was released: a later tutorial can complete.
    await tester.pumpWidget(harness.app());
    await tester.tap(find.text('start'));
    await _settle(tester);
    expect(harness.marks, 2);
  });
}
