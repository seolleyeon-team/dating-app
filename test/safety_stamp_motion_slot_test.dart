import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/screens/safety_stamp_screen.dart';
import 'package:seolleyeon/features/chat/widgets/safety_stamp_motion/safety_stamp_slot_motion.dart';

void main() {
  test('stamp source and animation selection preserve the source contract', () {
    expect(
      safetyStampModelSource(isWeb: true),
      'assets/assets/models/stamp_scene_animated.glb',
    );
    expect(safetyStampModelSource(isWeb: false), safetyStampModelAsset);
    expect(selectSafetyStampAnimationName(['Idle', 'Stamp']), 'Stamp');
    expect(SafetyStampMotionTiming.petalEndMs, 2400);
    expect(
      SafetyStampMotionTiming.impactMs - SafetyStampMotionTiming.stampStartMs,
      500,
    );
    expect(
      SafetyStampMotionTiming.stampExitMs -
          SafetyStampMotionTiming.stampStartMs,
      1100,
    );
  });

  testWidgets('the two board slots keep independent pressed-petal states', (
    tester,
  ) async {
    Widget board({required bool partnerStamped}) {
      return MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 360,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: 186,
                    child: SafetyStampSlotMotion(
                      timeline: partnerStamped ? 1 : 0,
                      isVisible: partnerStamped,
                      forceSettled: partnerStamped,
                      stickerSize: 210,
                      settledRotationDeg: 5,
                      enable3d: false,
                    ),
                  ),
                  const SizedBox(height: 14),
                  const SizedBox(
                    height: 186,
                    child: SafetyStampSlotMotion(
                      timeline: 1,
                      isVisible: true,
                      forceSettled: true,
                      stickerSize: 260,
                      settledRotationDeg: -3,
                      enable3d: false,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    Finder pressedPetals() => find.byWidgetPredicate(
      (widget) =>
          widget is Image &&
          widget.image is AssetImage &&
          (widget.image as AssetImage).assetName == 'cherrysticker-pressed.png',
    );

    await tester.pumpWidget(board(partnerStamped: false));
    expect(pressedPetals(), findsOneWidget);

    await tester.pumpWidget(board(partnerStamped: true));
    await tester.pump();
    expect(pressedPetals(), findsNWidgets(2));
  });

  testWidgets('the applied screen keeps partner and my stamp as two slots', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: SafetyStampScreen(
          roomId: '',
          promiseId: '',
          currentUserId: 'preview-me',
          partnerId: 'preview-partner',
          partnerName: '상대방',
          myName: '나',
          motionPreviewMode: true,
          motion3dEnabled: false,
        ),
      ),
    );

    expect(find.text('상대방님 칸'), findsOneWidget);
    expect(find.text('내 칸'), findsOneWidget);
    expect(find.text('도장 찍기'), findsOneWidget);
    expect(find.byKey(const ValueKey('pressed-petal')), findsOneWidget);

    await tester.tap(find.text('도장 찍기'));
    await tester.pump();
    expect(find.text('도장 처리 중...'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump(SafetyStampMotionTiming.total);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 850));

    expect(find.byKey(const ValueKey('pressed-petal')), findsNWidgets(2));
    expect(find.text('완료'), findsNWidgets(2));
  });
}
