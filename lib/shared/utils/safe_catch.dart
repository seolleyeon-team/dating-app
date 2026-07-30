import 'package:flutter/foundation.dart';

import 'privacy_log_utils.dart';

/// Logs a caught error without swallowing it silently.
void logCaughtError(String tag, Object error, [StackTrace? stackTrace]) {
  debugPrint('[$tag] ${PrivacyLogUtils.errorSummary(error)}');
  if (stackTrace != null && kDebugMode) {
    debugPrint('[$tag] stackType=${stackTrace.runtimeType}');
  }
}

/// Parses an enum by [Enum.name]. Unknown values are logged and return null.
T? enumByNameOrNull<T extends Enum>(
  List<T> values,
  String? name, {
  String tag = 'EnumParse',
}) {
  final trimmed = name?.trim();
  if (trimmed == null || trimmed.isEmpty) return null;
  for (final value in values) {
    if (value.name == trimmed) return value;
  }
  debugPrint('[$tag] unknown enum name=$trimmed for $T');
  return null;
}
