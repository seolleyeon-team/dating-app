import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/onboarding_route_args.dart';
import 'package:seolleyeon/features/onboarding/screens/interests_selection_screen.dart';
import 'package:seolleyeon/router/route_names.dart';

Future<void> _pumpRepairScreen(
  WidgetTester tester, {
  Future<List<String>> Function()? loadInterests,
  Future<void> Function(List<String>)? saveInterests,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: InterestsSelectionScreen(
        mode: InterestsSelectionMode.prerequisiteRepair,
        loadInterests: loadInterests,
        saveInterests: saveInterests,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<Future<bool?>> _pushRepairScreen(
  WidgetTester tester, {
  Future<List<String>> Function()? loadInterests,
  Future<void> Function(List<String>)? saveInterests,
}) async {
  late BuildContext rootContext;
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) {
          rootContext = context;
          return const SizedBox.shrink();
        },
      ),
    ),
  );
  final result = Navigator.of(rootContext).push<bool>(
    MaterialPageRoute<bool>(
      builder: (_) => InterestsSelectionScreen(
        mode: InterestsSelectionMode.prerequisiteRepair,
        loadInterests: loadInterests,
        saveInterests: saveInterests,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return result;
}

void main() {
  group('관심사 선택 화면의 prerequisiteRepair 모드', () {
    testWidgets('기존 관심사를 미리 채우고 온보딩 진행 표시를 숨긴다', (tester) async {
      await _pumpRepairScreen(
        tester,
        loadInterests: () async => const ['넷플릭스'],
      );

      expect(find.text('관심사'), findsOneWidget);
      expect(find.text('관심사 등록 완료'), findsOneWidget);
      expect(find.text('다음'), findsNothing);
      expect(
        find.byKey(const ValueKey('interests-selection-progress')),
        findsNothing,
      );
      expect(find.text('넷플릭스'), findsWidgets);
    });

    testWidgets('관심사가 없으면 보충 완료 버튼을 비활성화한다', (tester) async {
      await _pumpRepairScreen(tester, loadInterests: () async => const []);

      final button = tester.widget<CupertinoButton>(
        find.byType(CupertinoButton),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('보충 화면에서 뒤로 가면 저장 없이 취소 결과로 돌아온다', (tester) async {
      var saveCalls = 0;
      final result = await _pushRepairScreen(
        tester,
        loadInterests: () async => const ['넷플릭스'],
        saveInterests: (_) async {
          saveCalls++;
        },
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(await result, isNull);
      expect(saveCalls, 0);
    });

    testWidgets('저장 성공 시 선택값을 한 번 저장하고 true로 돌아온다', (tester) async {
      final saved = <List<String>>[];
      final result = await _pushRepairScreen(
        tester,
        loadInterests: () async => const [],
        saveInterests: (interests) async {
          saved.add(List<String>.from(interests));
        },
      );

      final interest = find.text('넷플릭스').last;
      await tester.ensureVisible(interest);
      await tester.tap(interest);
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심사 등록 완료'));
      await tester.pumpAndSettle();

      expect(await result, isTrue);
      expect(saved, [
        const ['넷플릭스'],
      ]);
    });

    testWidgets('저장 실패 시 화면을 유지하고 재시도 문구와 선택값을 보존한다', (tester) async {
      await _pushRepairScreen(
        tester,
        loadInterests: () async => const [],
        saveInterests: (_) async {
          throw StateError('document-id-must-not-be-shown');
        },
      );

      final interest = find.text('넷플릭스').last;
      await tester.ensureVisible(interest);
      await tester.tap(interest);
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심사 등록 완료'));
      await tester.pumpAndSettle();

      expect(find.byType(InterestsSelectionScreen), findsOneWidget);
      expect(find.text('관심사를 저장하지 못했어요. 다시 시도해주세요.'), findsOneWidget);
      expect(
        find.textContaining('document-id-must-not-be-shown'),
        findsNothing,
      );
      expect(find.text('넷플릭스'), findsWidgets);
    });

    testWidgets('기존 온보딩 모드는 진행 표시와 다음 버튼을 유지하고 lifestyle로 이동한다', (
      tester,
    ) async {
      final pushedRoutes = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: InterestsSelectionScreen(
            loadInterests: () async => const [],
            saveInterests: (_) async {},
          ),
          onGenerateRoute: (settings) {
            pushedRoutes.add(settings.name ?? '');
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (_) => const SizedBox.shrink(),
            );
          },
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('interests-selection-progress')),
        findsOneWidget,
      );
      expect(find.text('다음'), findsOneWidget);
      expect(find.text('관심사 등록 완료'), findsNothing);

      await tester.tap(find.text('다음'));
      await tester.pumpAndSettle();

      expect(pushedRoutes, contains(RouteNames.onboardingLifestyle));
    });
  });
}
