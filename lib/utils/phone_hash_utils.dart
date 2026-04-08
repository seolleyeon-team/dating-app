import 'dart:convert';
import 'package:crypto/crypto.dart';

/// 전화번호 정규화 + SHA-256 해시 유틸.
/// 클라이언트/서버 양쪽에서 동일 알고리즘을 사용해야 한다.
class PhoneHashUtils {
  PhoneHashUtils._();

  /// 한국 전화번호를 canonical 형태 `+821012345678`로 변환.
  /// 유효하지 않으면 `null` 반환.
  static String? normalizeKoreanPhone(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return null;

    final hasPlus = trimmed.startsWith('+');
    final digits = trimmed.replaceAll(RegExp(r'[^\d]'), '');

    if (digits.length < 7) return null;

    // +82 or 82 prefix
    if ((hasPlus || !digits.startsWith('0')) && digits.startsWith('82')) {
      final local = digits.substring(2);
      // 10xxxxxxxx (10 digits) or 1012345678 without leading 0
      if (local.startsWith('10') && local.length >= 9 && local.length <= 11) {
        return '+82$local';
      }
      // 010xxxxxxxx (leading 0 preserved in some formats)
      if (local.startsWith('0') && local.length >= 10 && local.length <= 12) {
        return '+82${local.substring(1)}';
      }
      return null;
    }

    // 010-xxxx-xxxx → +821012345678
    if (digits.startsWith('0')) {
      if (digits.length >= 10 && digits.length <= 11) {
        return '+82${digits.substring(1)}';
      }
      return null;
    }

    // bare 1012345678
    if (digits.startsWith('10') && digits.length >= 9 && digits.length <= 11) {
      return '+82$digits';
    }

    return null;
  }

  /// SHA-256 해시 (lowercase hex).
  static String hashPhone(String normalizedPhone) {
    final bytes = utf8.encode(normalizedPhone);
    return sha256.convert(bytes).toString();
  }

  /// normalize → hash. 실패 시 `null`.
  static String? normalizeAndHash(String rawPhone) {
    final normalized = normalizeKoreanPhone(rawPhone);
    if (normalized == null) return null;
    return hashPhone(normalized);
  }
}
