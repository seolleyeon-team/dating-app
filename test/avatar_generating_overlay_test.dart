import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generating_overlay.dart';

void main() {
  group('AvatarGeneratingOverlay', () {
    testWidgets('renders spinner and Korean text fragments when visible', (
      tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: AvatarGeneratingOverlay(visible: true)),
        ),
      );
      await tester.pump();

      expect(find.text('아바타 생성중...'), findsOneWidget);
      expect(find.textContaining('프로필에는 실제 사진이 아닌'), findsOneWidget);
      expect(find.textContaining('안전한 프로필 이미지를 만들고 있어요.'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('renders nothing of substance when hidden', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: AvatarGeneratingOverlay(visible: false)),
        ),
      );
      await tester.pump();

      expect(find.text('아바타 생성중...'), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });
  });
}
