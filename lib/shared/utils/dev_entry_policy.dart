import 'package:flutter/foundation.dart';

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

  /// True only in debug builds, unless a test says otherwise.
  static bool get allowTestAccountEntry => _testOverride ?? kDebugMode;

  @visibleForTesting
  static void debugSetTestAccountEntry(bool? value) {
    _testOverride = value;
  }
}
