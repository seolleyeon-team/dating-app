import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';

const _channel = MethodChannel('com.yonsei.dating/kakao_util');

/// Android에서만 동작. 카카오 개발자 콘솔에 등록할 키 해시 반환.
Future<String?> getAndroidKeyHash() async {
  if (kIsWeb) return null;
  try {
    final hash = await _channel.invokeMethod<String>('getKeyHash');
    return hash;
  } catch (_) {
    return null;
  }
}
