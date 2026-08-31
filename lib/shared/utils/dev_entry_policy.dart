import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show appFlavor;

/// Controls entry points that skip Kakao login and Yonsei student verification.
///
/// Student verification is the product's trust boundary. Everything downstream
/// of it — recommendations, chat, 무물, community — assumes the account behind
/// the session belongs to a verified student. Any shipped path around it puts
/// unverified accounts into all of those surfaces at once, so these entry
/// points must not exist in release builds.
class DevEntryPolicy {
  const DevEntryPolicy._();

  static bool? _testOverride;

  /// Enabled for debug builds and the isolated staging flavor only.
  ///
  /// Never enable this in production: it bypasses Kakao login and student
  /// verification by entering as `fake_user_1`.
  static bool get allowTestAccountEntry =>
      _testOverride ?? (kDebugMode || appFlavor == 'staging');

  @visibleForTesting
  static void debugSetTestAccountEntry(bool? value) {
    _testOverride = value;
  }
}
