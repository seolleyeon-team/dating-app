import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/app.dart';

void main() {
  testWidgets('App launches successfully', (tester) async {
    await tester.pumpWidget(
      const SeolleyeonApp(
        testHome: Scaffold(body: SizedBox(key: Key('app-test-home'))),
      ),
    );

    expect(find.byKey(const Key('app-test-home')), findsOneWidget);
  });
}
