import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class ScreenSecurityService {
  ScreenSecurityService._();

  static final ScreenSecurityService instance = ScreenSecurityService._();

  static const MethodChannel _channel = MethodChannel(
    'com.yonsei.dating/screen_security',
  );
  int _sensitiveScreenDepth = 0;

  Future<void> enableProtection() async {
    if (kIsWeb) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('enableProtection');
    } catch (e, st) {
      debugPrint('[ScreenSecurity] enableProtection failed: $e\n$st');
    }
  }

  Future<void> enterSensitiveScreen() async {
    if (kIsWeb) {
      return;
    }

    _sensitiveScreenDepth += 1;
    if (_sensitiveScreenDepth != 1) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('enableSensitiveProtection');
    } catch (e, st) {
      debugPrint('[ScreenSecurity] enableSensitiveProtection failed: $e\n$st');
    }
  }

  Future<void> exitSensitiveScreen() async {
    if (kIsWeb) {
      return;
    }

    if (_sensitiveScreenDepth == 0) {
      return;
    }

    _sensitiveScreenDepth -= 1;
    if (_sensitiveScreenDepth != 0) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('disableSensitiveProtection');
    } catch (e, st) {
      debugPrint('[ScreenSecurity] disableSensitiveProtection failed: $e\n$st');
    }
  }
}
