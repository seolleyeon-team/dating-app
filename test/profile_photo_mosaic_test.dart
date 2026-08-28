import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/widgets/profile_photo_mosaic.dart';

void main() {
  testWidgets('lays out the featured photo and five supporting photos', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Center(
          child: SizedBox(
            width: 320,
            child: ProfilePhotoMosaic(
              gap: 10,
              featuredBadge: const Text(
                '대표 사진',
                key: ValueKey('featured-badge'),
              ),
              itemBuilder: (_, index) =>
                  ColoredBox(key: ValueKey('photo-$index'), color: Colors.pink),
            ),
          ),
        ),
      ),
    );

    final featured = tester.getSize(find.byKey(const ValueKey('photo-0')));
    final secondary = tester.getSize(find.byKey(const ValueKey('photo-1')));
    final featuredTop = tester.getTopLeft(
      find.byKey(const ValueKey('photo-0')),
    );
    final bottomLeft = tester.getTopLeft(find.byKey(const ValueKey('photo-3')));

    expect(featured, const Size(210, 210));
    expect(secondary, const Size(100, 100));
    expect(bottomLeft.dy - featuredTop.dy, 220);
    for (var index = 0; index < 6; index++) {
      expect(find.byKey(ValueKey('photo-$index')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('featured-badge')), findsOneWidget);
  });
}
