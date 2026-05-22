import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_selection_dialog.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_tile.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';

List<AvatarCandidate> _mockCandidates({int count = 4}) {
  return List<AvatarCandidate>.generate(
    count,
    (i) => AvatarCandidate(
      candidateId: 'cand_$i',
      previewUrl: 'https://example.invalid/preview_$i.png',
    ),
  );
}

Widget _harness({
  required List<AvatarCandidate> candidates,
  bool isApproving = false,
  String? errorMessage,
  Future<void> Function(AvatarCandidate)? onConfirm,
}) {
  return MaterialApp(
    home: Scaffold(
      body: AvatarCandidateSelectionDialog(
        candidates: candidates,
        isApproving: isApproving,
        errorMessage: errorMessage,
        onConfirm:
            onConfirm ??
            (_) async {
              // no-op
            },
      ),
    ),
  );
}

/// 모달이 한 화면에 들어가는 모바일 사이즈로 테스트 서피스를 강제 설정한다.
Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 1100);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  group('AvatarCandidateSelectionDialog', () {
    testWidgets('shows headline lines and subtitle', (tester) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(_harness(candidates: _mockCandidates()));
      await tester.pump();

      expect(find.textContaining('프로필에 지정할'), findsOneWidget);
      expect(find.textContaining('아바타를 선택해주세요'), findsOneWidget);
      expect(find.text('선택한 아바타만 프로필에 표시돼요.'), findsOneWidget);
    });

    testWidgets('confirm button is disabled before any candidate is selected', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(_harness(candidates: _mockCandidates()));
      await tester.pump();

      final btn = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(btn.onPressed, isNull);
      expect(find.text('이 사진으로 할게요!'), findsOneWidget);
    });

    testWidgets('tapping a candidate enables the confirm button', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(_harness(candidates: _mockCandidates()));
      await tester.pump();

      await tester.tap(find.byType(AvatarCandidateTile).first);
      await tester.pump();

      final btn = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(btn.onPressed, isNotNull);
    });

    testWidgets('confirm button shows 저장하는 중... while approving', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(
        _harness(candidates: _mockCandidates(), isApproving: true),
      );
      await tester.pump();

      expect(find.text('저장하는 중...'), findsOneWidget);
      expect(find.text('이 사진으로 할게요!'), findsNothing);

      final btn = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      expect(btn.onPressed, isNull);
    });

    testWidgets('shows empty-state message when no candidates returned', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(_harness(candidates: const []));
      await tester.pump();

      expect(find.textContaining('안전한 아바타 후보를 만들지 못했어요'), findsOneWidget);
    });

    testWidgets('renders error banner when errorMessage is supplied', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      await tester.pumpWidget(
        _harness(
          candidates: _mockCandidates(),
          errorMessage: '아바타 저장에 실패했어요. 다시 한 번 선택해주세요.',
        ),
      );
      await tester.pump();

      expect(find.text('아바타 저장에 실패했어요. 다시 한 번 선택해주세요.'), findsOneWidget);
    });

    testWidgets('onConfirm fires with the selected candidate', (tester) async {
      await _useMobileSurface(tester);
      final completer = Completer<AvatarCandidate>();
      await tester.pumpWidget(
        _harness(
          candidates: _mockCandidates(),
          onConfirm: (c) async {
            completer.complete(c);
          },
        ),
      );
      await tester.pump();

      await tester.tap(find.byType(AvatarCandidateTile).at(1));
      await tester.pump();
      await tester.tap(find.text('이 사진으로 할게요!'));
      await tester.pump();

      final tapped = await completer.future.timeout(const Duration(seconds: 2));
      expect(tapped.candidateId, 'cand_1');
    });
  });
}
