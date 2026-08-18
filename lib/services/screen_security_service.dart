import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class ScreenSecurityService {
  ScreenSecurityService._();

  static final ScreenSecurityService instance = ScreenSecurityService._();

  static const MethodChannel _channel = MethodChannel(
    'com.seolleyeon.app/screen_security',
  );
  int _sensitiveScreenDepth = 0;

  Future<void> enableProtection() async {
    if (kIsWeb) {
      return;
    }

    try {
      await _channel.invokeMethod<void>('enableProtection');
    } catch (e) {
      debugPrint(
        '[ScreenSecurity] enableProtection failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
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
    } catch (e) {
      debugPrint(
        '[ScreenSecurity] enableSensitiveProtection failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
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
    } catch (e) {
      debugPrint(
        '[ScreenSecurity] disableSensitiveProtection failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }
}
