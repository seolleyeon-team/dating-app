import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// B-19: nothing the app stores locally may be backed up to the user's
/// Google account or copied to another phone by device-to-device transfer.
///
/// What lives on the device (see data_extraction_rules.xml): the Firebase
/// Auth session store, the cached appUserId / Yonsei email / verification
/// markers, onboarding drafts, the safety-stamp location log, pending invite
/// and identity-verification tokens (SharedPreferences) and the Firestore
/// offline cache (chat and profile documents). The server is the source of
/// truth for all of it.
void main() {
  final manifest = File(
    'android/app/src/main/AndroidManifest.xml',
  ).readAsStringSync();

  /// The `<application ...>` opening tag with its attributes.
  String applicationTag() {
    final match = RegExp(r'<application\b[^>]*>').firstMatch(manifest);
    expect(match, isNotNull, reason: 'manifest must declare <application>');
    return match!.group(0)!;
  }

  String? applicationAttribute(String name) {
    final match = RegExp(
      'android:$name="([^"]*)"',
    ).firstMatch(applicationTag());
    return match?.group(1);
  }

  /// `domain` values of every `<exclude>` directly inside `<section>`.
  Set<String> excludedDomains(String xml, String section) {
    final body = RegExp(
      '<$section>([\\s\\S]*?)</$section>',
    ).firstMatch(xml)?.group(1);
    expect(body, isNotNull, reason: 'missing <$section> section');
    return RegExp(
      r'<exclude\s+domain="([^"]+)"\s+path="\."\s*/>',
    ).allMatches(body!).map((match) => match.group(1)!).toSet();
  }

  String stripComments(String xml) =>
      xml.replaceAll(RegExp(r'<!--[\s\S]*?-->'), '');

  test('Auto Backup is disabled on the application', () {
    expect(
      applicationAttribute('allowBackup'),
      'false',
      reason:
          'a missing attribute defaults to true and backs up the Firebase '
          'Auth session and the Firestore cache',
    );
  });

  test('the application points at both rule files', () {
    expect(
      applicationAttribute('dataExtractionRules'),
      '@xml/data_extraction_rules',
    );
    expect(
      applicationAttribute('fullBackupContent'),
      '@xml/full_backup_content',
    );
  });

  test('no manifest merge override can re-enable backup', () {
    final tag = applicationTag();
    expect(tag, isNot(contains('tools:remove')));
    expect(tag, isNot(contains('tools:replace')));
    for (final variant in ['debug', 'profile']) {
      final file = File('android/app/src/$variant/AndroidManifest.xml');
      if (!file.existsSync()) continue;
      final source = file.readAsStringSync();
      expect(source, isNot(contains('allowBackup')), reason: variant);
      expect(source, isNot(contains('dataExtractionRules')), reason: variant);
      expect(source, isNot(contains('fullBackupContent')), reason: variant);
    }
  });

  test('API 31+: cloud backup and device transfer exclude every domain', () {
    final xml = stripComments(
      File(
        'android/app/src/main/res/xml/data_extraction_rules.xml',
      ).readAsStringSync(),
    );
    const required = {
      'root',
      'file',
      'database',
      'sharedpref',
      'external',
      'device_root',
      'device_file',
      'device_database',
      'device_sharedpref',
    };
    for (final section in ['cloud-backup', 'device-transfer']) {
      expect(
        excludedDomains(xml, section),
        containsAll(required),
        reason: '<$section> must exclude every storage domain',
      );
    }
    expect(
      xml,
      isNot(contains('<include')),
      reason: 'an <include> turns the file into an allowlist of backed-up data',
    );
    // `allowBackup="false"` does not stop device-to-device transfer for apps
    // targeting API 31+, so the section must exist on its own.
    expect(xml, contains('<device-transfer>'));
  });

  test('API 23-30: the legacy rule file excludes every domain', () {
    final xml = stripComments(
      File(
        'android/app/src/main/res/xml/full_backup_content.xml',
      ).readAsStringSync(),
    );
    expect(
      excludedDomains(xml, 'full-backup-content'),
      containsAll({'root', 'file', 'database', 'sharedpref', 'external'}),
    );
    expect(xml, isNot(contains('<include')));
  });

  test('the user-visible application attributes are untouched', () {
    final tag = applicationTag();
    expect(tag, contains(r'android:name="${applicationName}"'));
    expect(tag, contains('android:icon="@mipmap/ic_launcher"'));
    expect(tag, contains('android:label='));
  });
}
