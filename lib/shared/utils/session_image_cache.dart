import 'package:flutter/painting.dart';

/// B-15: decoded images outlive the widgets that showed them. The process-wide
/// [ImageCache] keeps the previous account's pictures (consent-gated real
/// photos among them) in memory after a logout or an account switch. Nothing
/// is ever written to disk — the client has no image disk cache — so emptying
/// this cache is the whole isolation step.
void clearSessionImageCache() {
  try {
    PaintingBinding.instance.imageCache
      ..clear()
      ..clearLiveImages();
  } catch (_) {
    // No binding yet (a pure unit test, or a reset before runApp): nothing
    // has been decoded.
  }
}
