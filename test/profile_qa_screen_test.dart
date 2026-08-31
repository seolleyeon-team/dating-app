import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seolleyeon/features/onboarding/screens/profile_qa_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  });

  testWidgets(
    'keeps the answer controller and IME composing range during rebuilds',
    (tester) async {
      SharedPreferences.setMockInitialValues({});

      await tester.pumpWidget(const MaterialApp(home: ProfileQaScreen()));
      await tester.pump();

      final fieldFinder = find.byType(TextField);
      expect(fieldFinder, findsOneWidget);

      final originalController = tester
          .widget<TextField>(fieldFinder)
          .controller;
      expect(originalController, isNotNull);

      await tester.tap(fieldFinder);
      await tester.showKeyboard(fieldFinder);
      tester.testTextInput.updateEditingValue(
        const TextEditingValue(
          text: 'ㅎ',
          selection: TextSelection.collapsed(offset: 1),
          composing: TextRange(start: 0, end: 1),
        ),
      );
      await tester.pump();

      final rebuiltController = tester
          .widget<TextField>(fieldFinder)
          .controller;
      expect(identical(originalController, rebuiltController), isTrue);
      expect(
        rebuiltController!.value.composing,
        const TextRange(start: 0, end: 1),
      );
    },
  );
}
