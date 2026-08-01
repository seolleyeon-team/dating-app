import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/models/avatar_source_consent.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_source_consent_controls.dart';

void main() {
  test('avatar source consent defaults optional purposes to false', () {
    const consent = AvatarSourceConsent();

    expect(consent.avatarGeneration, isTrue);
    expect(consent.clipRecommendation, isFalse);
    expect(consent.sourcePhotoRetention, isFalse);
    expect(consent.toPayloadMap(), {
      'avatarGeneration': true,
      'clipRecommendation': false,
      'sourcePhotoRetention': false,
    });
  });

  testWidgets(
    'controls expose separate optional toggles and lock when source starts',
    (tester) async {
      var consent = const AvatarSourceConsent();
      var chatDisclosure = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AvatarSourceConsentControls(
              value: consent,
              locked: false,
              onChanged: (value) => consent = value,
            ),
          ),
        ),
      );

      expect(find.text('아바타 생성 동의'), findsOneWidget);
      expect(find.textContaining('익명'), findsNothing);
      expect(
        tester
            .widget<CheckboxListTile>(
              find.byKey(AvatarSourceConsentControls.clipRecommendationKey),
            )
            .value,
        isFalse,
      );
      expect(
        tester
            .widget<CheckboxListTile>(
              find.byKey(AvatarSourceConsentControls.sourcePhotoRetentionKey),
            )
            .value,
        isFalse,
      );

      await tester.tap(
        find.byKey(AvatarSourceConsentControls.clipRecommendationKey),
      );
      await tester.pump();
      expect(consent.clipRecommendation, isTrue);
      expect(consent.sourcePhotoRetention, isFalse);
      expect(chatDisclosure, isFalse);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AvatarSourceConsentControls(
              value: consent,
              locked: true,
              onChanged: (value) => consent = value,
            ),
          ),
        ),
      );

      expect(
        tester
            .widget<CheckboxListTile>(
              find.byKey(AvatarSourceConsentControls.clipRecommendationKey),
            )
            .onChanged,
        isNull,
      );
      expect(
        tester
            .widget<CheckboxListTile>(
              find.byKey(AvatarSourceConsentControls.sourcePhotoRetentionKey),
            )
            .onChanged,
        isNull,
      );
      expect(chatDisclosure, isFalse);
    },
  );
}
