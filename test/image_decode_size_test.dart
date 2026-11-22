import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/profile/widgets/friends_list_shared.dart';
import 'package:seolleyeon/shared/utils/image_decode_size.dart';
import 'package:seolleyeon/shared/widgets/capture_protected_image.dart';

const _url = 'https://example.invalid/avatar.png';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  double devicePixelRatio = 3,
}) async {
  tester.view.devicePixelRatio = devicePixelRatio;
  tester.view.physicalSize = Size(
    400 * devicePixelRatio,
    800 * devicePixelRatio,
  );
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: Center(child: child)),
    ),
  );
}

ImageProvider _providerOf(WidgetTester tester) =>
    tester.widget<Image>(find.byType(Image)).image;

void main() {
  group('ImageDecodeSize.widthFor', () {
    test('a covered avatar decodes at a small bucket, not the source size', () {
      // 48 logical px at 3x = 144 px, doubled for a covering fit = 288.
      expect(
        ImageDecodeSize.widthFor(box: const Size(48, 48), devicePixelRatio: 3),
        384,
      );
      expect(
        ImageDecodeSize.widthFor(
          box: const Size(48, 48),
          devicePixelRatio: 3,
          fit: BoxFit.contain,
        ),
        192,
      );
    });

    test('rounds up to a bucket so an animating box does not decode per '
        'frame', () {
      final widths = {
        for (var side = 40.0; side <= 120; side += 1)
          ImageDecodeSize.widthFor(box: Size(side, side), devicePixelRatio: 3),
      };
      expect(widths, {256, 384, 512, 768});
    });

    test('leaves the source resolution alone when it cannot know the size', () {
      expect(
        ImageDecodeSize.widthFor(
          box: const Size(double.infinity, 48),
          devicePixelRatio: 3,
        ),
        isNull,
      );
      expect(
        ImageDecodeSize.widthFor(box: Size.zero, devicePixelRatio: 3),
        isNull,
      );
      // Larger than the largest bucket: a full-screen photo on a tablet.
      expect(
        ImageDecodeSize.widthFor(
          box: const Size(900, 1200),
          devicePixelRatio: 3,
        ),
        isNull,
      );
    });
  });

  group('CaptureProtectedImage (Flutter image path)', () {
    testWidgets('a 48 px avatar is decoded at 384 px', (tester) async {
      await _pump(
        tester,
        const SizedBox(
          width: 48,
          height: 48,
          child: CaptureProtectedImage(
            imageUrl: _url,
            shape: CaptureProtectedImageShape.circle,
          ),
        ),
      );

      final provider = _providerOf(tester);
      expect(provider, isA<ResizeImage>());
      final resized = provider as ResizeImage;
      expect(resized.width, 384);
      expect(resized.height, isNull, reason: 'the aspect ratio is kept');
      expect(resized.allowUpscaling, isFalse);
      expect(resized.imageProvider, isA<NetworkImage>());
      expect((resized.imageProvider as NetworkImage).url, _url);
    });

    testWidgets('a larger box asks for a larger decode', (tester) async {
      await _pump(
        tester,
        const SizedBox(
          width: 160,
          height: 200,
          child: CaptureProtectedImage(imageUrl: _url),
        ),
      );

      // 200 px * 3 * 2 = 1200 -> 1536.
      expect((_providerOf(tester) as ResizeImage).width, 1536);
    });

    test('still loads through Image.network: memory only, nothing on disk', () {
      final source = File(
        'lib/shared/widgets/capture_protected_image.dart',
      ).readAsStringSync();
      expect(source, contains('Image.network('));
      for (final diskCache in [
        'CachedNetworkImage',
        'cached_network_image',
        'CacheManager',
        'File(',
      ]) {
        expect(source, isNot(contains(diskCache)), reason: diskCache);
      }
      // No image disk cache dependency exists for the widget to pick up.
      final pubspec = File('pubspec.yaml').readAsStringSync();
      expect(pubspec, isNot(contains('cached_network_image')));
      expect(pubspec, isNot(contains('flutter_cache_manager')));
    });
  });

  testWidgets('a friend list avatar is decoded at its 56 px size', (
    tester,
  ) async {
    await _pump(
      tester,
      const FriendAvatarWidget(imageUrl: _url, fallbackText: '민지'),
    );

    // 56 * 3 * 2 = 336 -> 384.
    final provider = _providerOf(tester);
    expect(provider, isA<ResizeImage>());
    expect((provider as ResizeImage).width, 384);
  });
}
