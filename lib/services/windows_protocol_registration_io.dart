import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:win32/win32.dart';

Future<void> ensureWindowsProtocolRegistration() async {
  if (kIsWeb || defaultTargetPlatform != TargetPlatform.windows) {
    return;
  }

  const scheme = 'seolleyeon';
  final executable = Platform.resolvedExecutable;
  final command = '"${_sanitize(executable)}" "%1"';
  final prefix = 'SOFTWARE\\Classes\\$scheme';

  try {
    _setRegistryString(prefix, '', 'URL:Seolleyeon');
    _setRegistryString(prefix, 'URL Protocol', '');
    _setRegistryString('$prefix\\DefaultIcon', '', executable);
    _setRegistryString('$prefix\\shell\\open\\command', '', command);
    debugPrint(
      '[DesktopProtocol] Registered Windows protocol '
      '$scheme:// -> $executable',
    );
  } catch (e, st) {
    debugPrint('[DesktopProtocol] Windows protocol registration failed: $e');
    debugPrint(st.toString());
  }
}

void _setRegistryString(String key, String valueName, String data) {
  final txtKey = TEXT(key);
  final txtValueName = TEXT(valueName);
  final txtData = TEXT(data);

  try {
    final result = RegSetKeyValue(
      HKEY_CURRENT_USER,
      txtKey,
      txtValueName,
      REG_SZ,
      txtData,
      (data.length * 2) + 2,
    );
    if (result != ERROR_SUCCESS) {
      throw WindowsException(result);
    }
  } finally {
    free(txtKey);
    free(txtValueName);
    free(txtData);
  }
}

String _sanitize(String value) {
  return value.replaceAll('"', '\\"');
}
