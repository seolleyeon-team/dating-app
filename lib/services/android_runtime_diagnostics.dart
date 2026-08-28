import 'package:flutter/services.dart';

/// Read-only facts supplied by Android about the currently installed package.
/// This is deliberately limited to App Check troubleshooting and does not
/// expose device IDs, account data, tokens, or application secrets.
class AndroidRuntimeDiagnostics {
  const AndroidRuntimeDiagnostics({
    required this.packageName,
    required this.versionName,
    required this.versionCode,
    required this.installerPackage,
    required this.signingCertificateSha256,
  });

  final String packageName;
  final String versionName;
  final String versionCode;
  final String installerPackage;
  final List<String> signingCertificateSha256;

  static const _channel = MethodChannel(
    'com.seolleyeon.app/runtime_diagnostics',
  );

  static Future<AndroidRuntimeDiagnostics> load() async {
    final raw = await _channel.invokeMapMethod<String, dynamic>('getAppCheck');
    if (raw == null) {
      throw StateError('Android runtime diagnostics returned no data.');
    }
    return AndroidRuntimeDiagnostics(
      packageName: _value(raw, 'packageName'),
      versionName: _value(raw, 'versionName'),
      versionCode: _value(raw, 'versionCode'),
      installerPackage: _value(raw, 'installerPackage'),
      signingCertificateSha256: _values(raw['signingCertificateSha256']),
    );
  }

  static String _value(Map<String, dynamic> raw, String key) =>
      raw[key]?.toString().trim().isNotEmpty == true
      ? raw[key].toString().trim()
      : '확인 불가';

  static List<String> _values(Object? value) {
    if (value is! List) return const ['확인 불가'];
    final values = value
        .map((entry) => entry.toString().trim())
        .where((entry) => entry.isNotEmpty)
        .toList(growable: false);
    return values.isEmpty ? const ['확인 불가'] : values;
  }
}
