import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/profile_edit_golden_comparator.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temporaryDirectory;
  late ProfileEditGoldenComparator comparator;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'profile-edit-golden-comparator-',
    );
    comparator = ProfileEditGoldenComparator(
      Uri.file(
        '${temporaryDirectory.path}${Platform.pathSeparator}case_test.dart',
      ),
    );
  });

  tearDown(() async {
    autoUpdateGoldenFiles = false;
    await temporaryDirectory.delete(recursive: true);
  });

  test('uses only the explicit approved filename allowlist', () {
    expect(
      ProfileEditGoldenComparator.precisionToleranceFor(
        'profile_edit_showcase_01_top.png',
      ),
      0.036,
    );
    expect(
      ProfileEditGoldenComparator.precisionToleranceFor(
        'profile_edit_mbti_selector.png',
      ),
      0.04,
    );
    expect(
      ProfileEditGoldenComparator.precisionToleranceFor(
        'profile_edit_unapproved.png',
      ),
      isNull,
    );
  });

  test('passes an allowlisted raster delta below its threshold', () async {
    final expected = base64Decode(_png10x10White);
    final actual = base64Decode(_png10x10ThreeBlack);
    await _writeGolden(temporaryDirectory, _topGolden, expected);

    expect(await comparator.compare(actual, _topGolden), isTrue);
  });

  test('fails an allowlisted delta above its threshold', () async {
    final expected = base64Decode(_png10x10White);
    final actual = base64Decode(_png10x10FourBlack);
    await _writeGolden(temporaryDirectory, _topGolden, expected);

    final error = await _captureFlutterError(
      () => comparator.compare(actual, _topGolden),
    );
    expect(error.message, contains('4.00%'));
    expect(error.message, contains('3.60%'));
    expect(error.message, contains('10x10'));
  });

  test('fails immediately when image dimensions differ', () async {
    final expected = base64Decode(_png10x10White);
    final actual = base64Decode(_png11x10White);
    await _writeGolden(temporaryDirectory, _topGolden, expected);

    final error = await _captureFlutterError(
      () => comparator.compare(actual, _topGolden),
    );
    expect(error.message, contains('10x10'));
    expect(error.message, contains('11x10'));
  });

  test('delegates a non-allowlisted golden to exact comparison', () async {
    final unapproved = Uri(path: 'goldens/unapproved.png');
    final expected = base64Decode(_png10x10White);
    await _writeGolden(temporaryDirectory, unapproved, expected);

    expect(
      ProfileEditGoldenComparator.precisionToleranceFor(
        unapproved.pathSegments.last,
      ),
      isNull,
    );
    expect(await comparator.compare(expected, unapproved), isTrue);
  });

  test('hard-fails auto-update mode and direct updates', () async {
    final expected = base64Decode(_png10x10White);
    await _writeGolden(temporaryDirectory, _topGolden, expected);
    autoUpdateGoldenFiles = true;

    await _captureFlutterError(() => comparator.compare(expected, _topGolden));
    await _captureFlutterError(() => comparator.update(_topGolden, expected));
  });

  test('rejects the historical 6.81 percent structural delta', () async {
    final expected = base64Decode(_png100x100WhiteRgb);
    final actual = base64Decode(_png100x100SixEightyOneBlackRgb);
    await _writeGolden(temporaryDirectory, _topGolden, expected);

    await _captureFlutterError(() => comparator.compare(actual, _topGolden));
  });

  test('does not admit a nine percent MBTI delta', () async {
    final mbtiGolden = Uri(path: 'goldens/profile_edit_mbti_selector.png');
    final expected = base64Decode(_png10x10White);
    final actual = base64Decode(_png10x10NineBlack);
    await _writeGolden(temporaryDirectory, mbtiGolden, expected);

    await _captureFlutterError(() => comparator.compare(actual, mbtiGolden));
  });
}

final _topGolden = Uri(path: 'goldens/profile_edit_showcase_01_top.png');

Future<void> _writeGolden(
  Directory temporaryDirectory,
  Uri golden,
  Uint8List bytes,
) async {
  final file = File(
    '${temporaryDirectory.path}${Platform.pathSeparator}${golden.path}',
  );
  await file.parent.create(recursive: true);
  await file.writeAsBytes(bytes);
}

Future<FlutterError> _captureFlutterError(
  Future<Object?> Function() action,
) async {
  try {
    await action();
  } on FlutterError catch (error) {
    return error;
  }
  fail('Expected a FlutterError.');
}

const _png10x10White =
    'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAHElEQVR4nGP8////fwYiABMxikBgVCFeQHTwAABpmgQQMCO55QAAAABJRU5ErkJggg==';
const _png10x10ThreeBlack =
    'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAI0lEQVR4nGNkYGD4zwAF///DmRiABZ8kMmBiIBIwjSpkwAMAkY8HD4bLKg4AAAAASUVORK5CYII=';
const _png10x10FourBlack =
    'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAI0lEQVR4nGNkYGD4z4AE/v9H4cIBCy4JdMBElCqGUYUM+AEAhZsHD/j4rMwAAAAASUVORK5CYII=';
const _png11x10White =
    'iVBORw0KGgoAAAANSUhEUgAAAAsAAAAKCAYAAABi8KSDAAAAHElEQVR4nGP8////fwYiAROxCkFgVDEyoF1oAAAKwQQQfHuKeQAAAABJRU5ErkJggg==';
const _png10x10NineBlack =
    'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAIklEQVR4nGNkYGD4z0AA/P//n4EFRBADmIhSxTCqkAE/AABJ1wcPUN88dAAAAABJRU5ErkJggg==';
const png100x100WhiteRgbaFixture =
    'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAABAElEQVR4nO3RQQ0AIBDAMMC/5+ONAvZoFSzZnplZZJzfAbwMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTEkxpAYQ2IMiTFktVwIYATE/szUowAAAABJRU5ErkJggg==';
const png100x100SixEightyOneBlackRgbaFixture =
    'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAABD0lEQVR4nO3WwQmAQAwAwSjXf8vn27eCi8wUEAILIcfM7CHj/HoB7gSJESRGkBhBYtbXC/zB3u89quvNYTznZMUIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCAxgsQIEiNIjCDTcgHX7gfFVBy9ogAAAABJRU5ErkJggg==';

const _png100x100WhiteRgb =
    'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAA5klEQVR4nO3SsREAIAwDMWD/ncMK+V6qXf35zsxh5y13iNV4ViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYg1tn7z/EDxbGcl84AAAAASUVORK5CYII=';
const _png100x100SixEightyOneBlackRgb =
    'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAA50lEQVR4nO3QsQ2AMBAEwYf+ezYtsE4Q8kx+0mlnAOB015xnrbU3vLaXB7q/PvAnYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYs17D+1hBrUEmQqgAAAAAElFTkSuQmCC';
