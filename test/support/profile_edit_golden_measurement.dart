import 'dart:io';

import 'package:flutter/foundation.dart';

/// Emits canonical Ubuntu evidence only on GitHub Actions Linux runners.
///
/// This diagnostic is confined to the temporary measurement branch. It does
/// not change comparison outcomes, thresholds, or approved golden files.
class ProfileEditGoldenMeasurement {
  const ProfileEditGoldenMeasurement._();

  static bool get enabled =>
      Platform.isLinux && Platform.environment['GITHUB_ACTIONS'] == 'true';

  static Future<void> report({
    required String filename,
    required Uint8List actualBytes,
    required Uint8List expectedBytes,
    required double diffPercent,
  }) async {
    if (!enabled) return;

    debugPrintSynchronously(
      'PROFILE_EDIT_GOLDEN_DIFF filename=$filename '
      'changed_pixel_ratio_pct=${(diffPercent * 100).toStringAsFixed(6)}',
      wrapWidth: 1000000,
    );
    if (filename != 'profile_edit_mbti_selector.png') return;

    final temporaryDirectory = await Directory.systemTemp.createTemp(
      'profile-edit-mbti-measurement-',
    );
    try {
      final expected = File('${temporaryDirectory.path}/expected.png');
      final actual = File('${temporaryDirectory.path}/actual.png');
      await expected.writeAsBytes(expectedBytes, flush: true);
      await actual.writeAsBytes(actualBytes, flush: true);

      final result = await Process.run('python3', [
        'scripts/profile_edit_golden_diff_analysis.py',
        expected.path,
        actual.path,
      ]);
      if (result.stdout.toString().trim().isNotEmpty) {
        debugPrintSynchronously(
          result.stdout.toString().trim(),
          wrapWidth: 1000000,
        );
      }
      if (result.exitCode != 0) {
        throw FlutterError(
          'Canonical MBTI diff analysis failed (${result.exitCode}): '
          '${result.stderr}',
        );
      }
    } finally {
      await temporaryDirectory.delete(recursive: true);
    }
  }
}
