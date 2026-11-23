import 'package:flutter/painting.dart';

/// Picks the resolution a network image is decoded at from the size it is
/// displayed at.
///
/// `Image.network` decodes at the source resolution unless told otherwise. A
/// 1024x1024 avatar shown in a 48 px circle then holds about 4 MB of decoded
/// pixels, so a list of a few dozen avatars fills the 100 MB image cache and
/// rows scrolled back into view are downloaded and decoded again (nothing is
/// cached on disk).
abstract final class ImageDecodeSize {
  /// Decode widths are rounded up to one of these so that a box whose size
  /// animates passes through a few decodes, not one per frame.
  static const List<int> buckets = [
    96,
    128,
    192,
    256,
    384,
    512,
    768,
    1024,
    1536,
    2048,
  ];

  /// The `cacheWidth` for an image displayed in [box], in physical pixels, or
  /// null to decode at the source resolution (unbounded box, or a box larger
  /// than the largest bucket).
  ///
  /// Only the width is constrained, so the aspect ratio is preserved and
  /// `ResizeImage` never upscales. With a covering fit the image may be wider
  /// than the box needs (a landscape photo in a square box is scaled by its
  /// height), so the target is doubled: enough for any photo up to 2:1.
  static int? widthFor({
    required Size box,
    required double devicePixelRatio,
    BoxFit fit = BoxFit.cover,
  }) {
    if (!box.width.isFinite || !box.height.isFinite) return null;
    if (box.isEmpty || devicePixelRatio <= 0) return null;
    final covering = fit == BoxFit.cover || fit == BoxFit.fill;
    final target = box.longestSide * devicePixelRatio * (covering ? 2 : 1);
    for (final bucket in buckets) {
      if (bucket >= target) return bucket;
    }
    return null;
  }
}
