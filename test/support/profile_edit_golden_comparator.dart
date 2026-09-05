import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'profile_edit_golden_measurement.dart';

/// Preserves the human-approved profile-edit goldens while isolating measured
/// OS-specific Skia, font, and shadow rasterization differences.
///
/// Structural geometry is verified independently by widget tests. Files not
/// listed in [_precisionToleranceByFilename] use Flutter's exact comparator.
class ProfileEditGoldenComparator extends LocalFileComparator {
  ProfileEditGoldenComparator(super.testFile);

  static const Map<String, double> _precisionToleranceByFilename = {
    'profile_edit_showcase_01_top.png': 0.036,
    'profile_edit_showcase_02_scroll.png': 0.034,
    'profile_edit_showcase_03_scroll.png': 0.031,
    'profile_edit_showcase_04_scroll.png': 0.032,
    'profile_edit_showcase_05_scroll.png': 0.028,
    'profile_edit_showcase_06_scroll.png': 0.028,
    'profile_edit_mbti_selector.png': 0.04,
  };

  /// Returns the changed-pixel-ratio threshold for an exact approved filename.
  @visibleForTesting
  static double? precisionToleranceFor(String filename) =>
      _precisionToleranceByFilename[filename];

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    _failIfUpdating(golden);

    final filename = golden.pathSegments.last;
    final precisionTolerance = precisionToleranceFor(filename);
    if (precisionTolerance == null) {
      return super.compare(imageBytes, golden);
    }

    final goldenBytes = Uint8List.fromList(await getGoldenBytes(golden));
    final actualImage = await _decode(imageBytes);
    final expectedImage = await _decode(goldenBytes);
    final actualDimensions = '${actualImage.width}x${actualImage.height}';
    final expectedDimensions = '${expectedImage.width}x${expectedImage.height}';

    if (actualDimensions != expectedDimensions) {
      actualImage.dispose();
      expectedImage.dispose();
      throw FlutterError(
        'Golden "$filename" dimension mismatch. '
        'Expected $expectedDimensions; actual $actualDimensions. '
        'Tolerance was not applied.',
      );
    }

    actualImage.dispose();
    expectedImage.dispose();
    final result = await GoldenFileComparator.compareLists(
      imageBytes,
      goldenBytes,
    );
    await ProfileEditGoldenMeasurement.report(
      filename: filename,
      actualBytes: imageBytes,
      expectedBytes: goldenBytes,
      diffPercent: result.diffPercent,
    );
    final passed = result.passed || result.diffPercent <= precisionTolerance;
    if (passed) {
      result.dispose();
      return true;
    }

    final actualPercent = (result.diffPercent * 100).toStringAsFixed(2);
    final allowedPercent = (precisionTolerance * 100).toStringAsFixed(2);
    if (ProfileEditGoldenMeasurement.enabled &&
        filename == 'profile_edit_mbti_selector.png') {
      final output = await generateFailureOutput(
        result,
        golden,
        basedir,
        key: 'canonical_ubuntu',
      );
      debugPrintSynchronously(
        'PROFILE_EDIT_GOLDEN_FAILURE_OUTPUT $output',
        wrapWidth: 1000000,
      );
    }
    result.dispose();
    throw FlutterError(
      'Profile-edit golden "$filename": actual $actualPercent%, '
      'allowed $allowedPercent%, dimensions $actualDimensions.',
    );
  }

  @override
  Future<void> update(Uri golden, Uint8List imageBytes) {
    throw FlutterError(
      'Golden updates are prohibited for the human-approved EXPECTED design: '
      '${golden.pathSegments.last}',
    );
  }

  void _failIfUpdating(Uri golden) {
    if (autoUpdateGoldenFiles) {
      throw FlutterError(
        'Golden update mode is prohibited for the human-approved EXPECTED '
        'design: ${golden.pathSegments.last}',
      );
    }
  }

  Future<ui.Image> _decode(Uint8List bytes) async {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    codec.dispose();
    return frame.image;
  }
}
