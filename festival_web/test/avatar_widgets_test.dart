import 'dart:convert';

import 'package:festival_web/avatar/avatar_candidate_dialog.dart';
import 'package:festival_web/avatar/avatar_generating_overlay.dart';
import 'package:festival_web/avatar/avatar_generation_models.dart';
import 'package:festival_web/avatar/avatar_photo_input.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('generating overlay shows privacy preserving Korean copy', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: AvatarGeneratingOverlay()));

    expect(find.text('아바타 생성중...'), findsOneWidget);
    expect(find.text('프로필에는 실제 사진이 아닌 아바타가 표시돼요.'), findsOneWidget);
    expect(find.text('잠시만 기다려주세요. 안전한 프로필 이미지를 만들고 있어요.'), findsOneWidget);
  });

  testWidgets('candidate dialog requires selection before approval', (
    tester,
  ) async {
    var approvedCandidateId = '';
    await tester.pumpWidget(
      MaterialApp(
        home: AvatarCandidateSelectionDialog(
          candidates: [
            AvatarCandidate(
              candidateId: 'cand_1',
              previewBytes: base64Decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lw9LrwAAAABJRU5ErkJggg==',
              ),
              previewMimeType: 'image/png',
            ),
            AvatarCandidate(
              candidateId: 'cand_2',
              previewBytes: base64Decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lw9LrwAAAABJRU5ErkJggg==',
              ),
              previewMimeType: 'image/png',
            ),
          ],
          approving: false,
          onApprove: (candidateId) => approvedCandidateId = candidateId,
        ),
      ),
    );

    expect(find.text('프로필에 지정할 아바타를 선택해주세요'), findsOneWidget);
    final approveButton = find.text('이 사진으로 할게요!');
    expect(
      tester
          .widget<ElevatedButton>(
            find.ancestor(
              of: approveButton,
              matching: find.byType(ElevatedButton),
            ),
          )
          .onPressed,
      isNull,
    );

    await tester.tap(find.bySemanticsLabel('아바타 후보 2'));
    await tester.pump();
    await tester.tap(approveButton);

    expect(approvedCandidateId, 'cand_2');
  });

  testWidgets(
    'photo input allows change before generation and blocks after lock',
    (tester) async {
      var pickCount = 0;
      var removeCount = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: AvatarPhotoInput(
            hasLocalPhoto: true,
            sourceLocked: false,
            approvedAvatarUrl: '',
            isBusy: false,
            fileName: 'face.png',
            onPick: () => pickCount++,
            onRemove: () => removeCount++,
          ),
        ),
      );

      await tester.tap(find.text('다시 선택'));
      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      expect(pickCount, 1);
      expect(removeCount, 1);

      await tester.pumpWidget(
        MaterialApp(
          home: AvatarPhotoInput(
            hasLocalPhoto: true,
            sourceLocked: true,
            approvedAvatarUrl: '',
            isBusy: false,
            fileName: 'face.png',
            onPick: () => pickCount++,
            onRemove: () => removeCount++,
          ),
        ),
      );

      expect(find.text('아바타 생성이 시작되어 사진을 변경할 수 없어요.'), findsOneWidget);
      expect(find.text('다시 선택'), findsNothing);
      expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
    },
  );
}
