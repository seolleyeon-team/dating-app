import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/widgets/ai_preference_progressive_blur_surface.dart';

void main() {
  testWidgets(
    'composites progressive blur above one sharp base with no sharp top cover',
    (tester) async {
      final image = MemoryImage(
        Uint8List.fromList(<int>[
          0x89,
          0x50,
          0x4e,
          0x47,
          0x0d,
          0x0a,
          0x1a,
          0x0a,
          0x00,
          0x00,
          0x00,
          0x0d,
          0x49,
          0x48,
          0x44,
          0x52,
          0x00,
          0x00,
          0x00,
          0x01,
          0x00,
          0x00,
          0x00,
          0x01,
          0x08,
          0x06,
          0x00,
          0x00,
          0x00,
          0x1f,
          0x15,
          0xc4,
          0x89,
          0x00,
          0x00,
          0x00,
          0x0d,
          0x49,
          0x44,
          0x41,
          0x54,
          0x78,
          0x9c,
          0x63,
          0xf8,
          0xcf,
          0xc0,
          0xf0,
          0x1f,
          0x00,
          0x05,
          0x00,
          0x01,
          0xff,
          0x89,
          0x99,
          0x3d,
          0x1d,
          0x00,
          0x00,
          0x00,
          0x00,
          0x49,
          0x45,
          0x4e,
          0x44,
          0xae,
          0x42,
          0x60,
          0x82,
        ]),
      );

      await tester.pumpWidget(
        CupertinoApp(home: AiPreferenceProgressiveBlurSurface(image: image)),
      );

      final visualStackFinder = find.byKey(
        const Key('ai_preference_visual_stack'),
      );
      expect(visualStackFinder, findsOneWidget);

      final visualStack = tester.widget<Stack>(visualStackFinder);
      expect(
        visualStack.children.first.key,
        const Key('ai_preference_sharp_base'),
      );
      expect(
        visualStack.children.last.key,
        const Key('ai_preference_bottom_dark_gradient'),
      );
      expect(
        visualStack.children.map((child) => child.key),
        isNot(contains(const Key('ai_preference_sharp_top_cover'))),
      );

      final images = tester
          .widgetList<Image>(
            find.descendant(
              of: visualStackFinder,
              matching: find.byType(Image),
            ),
          )
          .toList();
      expect(images.length, 7);
      expect(images.every((widget) => widget.image == image), isTrue);
      expect(images.every((widget) => widget.fit == BoxFit.cover), isTrue);
      expect(
        find.descendant(
          of: visualStackFinder,
          matching: find.byType(ImageFiltered),
        ),
        findsNWidgets(6),
      );
      expect(
        find.descendant(
          of: visualStackFinder,
          matching: find.byType(ShaderMask),
        ),
        findsNWidgets(6),
      );
    },
  );
}
