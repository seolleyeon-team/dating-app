import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/session_image_cache.dart';

Future<ui.Image> _onePixelImage() async {
  final completer = ui.ImmutableBuffer.fromUint8List(
    Uint8List.fromList(const [255, 0, 0, 255]),
  );
  final descriptor = ui.ImageDescriptor.raw(
    await completer,
    width: 1,
    height: 1,
    pixelFormat: ui.PixelFormat.rgba8888,
  );
  final codec = await descriptor.instantiateCodec();
  return (await codec.getNextFrame()).image;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'B-15: a session reset leaves no decoded picture of the previous account',
    () async {
      final cache = PaintingBinding.instance.imageCache;
      cache
        ..clear()
        ..clearLiveImages();

      final image = await _onePixelImage();
      final completer = OneFrameImageStreamCompleter(
        Future<ImageInfo>.value(ImageInfo(image: image)),
      );
      // A listener keeps the entry "live", like a widget still on screen
      // while the logout runs.
      final listener = ImageStreamListener((_, _) {});
      completer.addListener(listener);
      cache.putIfAbsent('previous-account-photo', () => completer);
      await Future<void>.delayed(Duration.zero);
      expect(cache.containsKey('previous-account-photo'), isTrue);
      expect(cache.liveImageCount, greaterThan(0));

      clearSessionImageCache();

      expect(cache.containsKey('previous-account-photo'), isFalse);
      expect(cache.currentSize, 0);
      expect(cache.liveImageCount, 0);
      completer.removeListener(listener);
    },
  );

  test(
    'B-15: every session reset of the auth provider clears the image cache',
    () {
      final provider = File(
        'lib/providers/auth_provider.dart',
      ).readAsStringSync();
      final reset = provider.substring(
        provider.indexOf('void _resetSessionState() {'),
      );
      final body = reset.substring(0, reset.indexOf('\n  }'));
      expect(body, contains('clearSessionImageCache();'));
      // Logout and an external sign-out both go through that reset.
      final logout = provider.substring(
        provider.indexOf('Future<void> logout() async {'),
      );
      expect(
        logout.substring(0, logout.indexOf('\n  }')),
        contains('_resetSessionState();'),
      );
    },
  );

  test('B-15: the client still has no image disk cache to clear', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, isNot(contains('cached_network_image')));
    expect(pubspec, isNot(contains('flutter_cache_manager')));
  });
}
