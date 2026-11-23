import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// AUD-23: Firebase Hosting served no `nosniff` / frame / referrer headers,
/// every clean URL except the email link was cached for an hour, and the two
/// published apple-app-site-association files had drifted apart.
///
/// The response headers themselves are verified against the Hosting emulator
/// (see docs/audits/production_readiness_2026-10/07-residual-remediation.md);
/// this test pins the configuration so a new rewrite or a hand edit cannot
/// silently drop them.
void main() {
  late Map<String, dynamic> hosting;
  late List<Map<String, dynamic>> headerRules;

  setUpAll(() {
    final firebase =
        jsonDecode(File('firebase.json').readAsStringSync())
            as Map<String, dynamic>;
    hosting = firebase['hosting'] as Map<String, dynamic>;
    headerRules = (hosting['headers'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
  });

  Map<String, String> collect(Iterable<Map<String, dynamic>> rules) {
    final result = <String, String>{};
    for (final rule in rules) {
      for (final header
          in (rule['headers'] as List<dynamic>).cast<Map<String, dynamic>>()) {
        result[header['key'] as String] = header['value'] as String;
      }
    }
    return result;
  }

  Map<String, String> headersFor(String source) =>
      collect(headerRules.where((rule) => rule['source'] == source));

  group('Hosting security headers', () {
    test('every response forbids MIME sniffing and trims the referrer', () {
      // `**` does not descend into dot directories, so /.well-known needs its
      // own rule.
      for (final source in ['**', '/.well-known/**']) {
        final headers = headersFor(source);
        expect(headers['X-Content-Type-Options'], 'nosniff', reason: source);
        // Invite and email-link URLs carry tokens in the query string: a
        // cross-origin request (fonts, the Kakao SDK) must only see the
        // origin.
        expect(
          headers['Referrer-Policy'],
          'strict-origin-when-cross-origin',
          reason: source,
        );
      }
    });

    test('pages cannot be framed by another origin', () {
      // An RE2 rule (no look-ahead available) that matches every path except
      // Firebase's reserved /__/ namespace, so the Auth handler and iframe
      // can never be affected by it.
      final frameRules = headerRules
          .where((rule) => rule.containsKey('regex'))
          .toList();
      expect(frameRules, hasLength(1));
      expect(frameRules.single.containsKey('source'), isFalse);
      final pattern = RegExp(frameRules.single['regex'] as String);
      for (final path in [
        '/',
        '/index.html',
        '/privacy',
        '/invite/friend',
        '/auth/email-link',
        '/.well-known/assetlinks.json',
        '/_',
        '/__',
        '/__x',
        '/a/__/b',
      ]) {
        expect(pattern.hasMatch(path), isTrue, reason: path);
      }
      for (final path in ['/__/auth/handler', '/__/auth/iframe', '/__/x']) {
        expect(pattern.hasMatch(path), isFalse, reason: path);
      }

      final frame = collect(frameRules);
      expect(frame['X-Frame-Options'], 'SAMEORIGIN');
      expect(frame['Content-Security-Policy'], "frame-ancestors 'self'");
      expect(headersFor('**').containsKey('X-Frame-Options'), isFalse);
    });

    test('no header rule widens framing or re-enables sniffing', () {
      for (final rule in headerRules) {
        for (final header
            in (rule['headers'] as List<dynamic>)
                .cast<Map<String, dynamic>>()) {
          final key = (header['key'] as String).toLowerCase();
          final value = (header['value'] as String).toLowerCase();
          if (key == 'x-frame-options') {
            expect(value, anyOf('sameorigin', 'deny'));
          }
          if (key == 'x-content-type-options') {
            expect(value, 'nosniff');
          }
          if (key == 'access-control-allow-origin') {
            expect(value, isNot('*'));
          }
        }
      }
    });
  });

  group('Hosting cache policy', () {
    test('every clean URL that serves a document is no-store', () {
      final rewrites = (hosting['rewrites'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      final documentSources = <String>{
        '/',
        '**/*.html',
        for (final rewrite in rewrites)
          if (rewrite['source'] != '**') rewrite['source'] as String,
      };
      for (final source in documentSources) {
        expect(
          headersFor(source)['Cache-Control'],
          'no-store',
          reason:
              '$source serves an HTML document; a cached copy would outlive a '
              'security fix to the landing page for up to an hour',
        );
      }
    });

    test('the email-link landing page stays no-store', () {
      expect(headersFor('/auth/email-link')['Cache-Control'], 'no-store');
      expect(headersFor('/auth/email-link/**')['Cache-Control'], 'no-store');
    });
  });

  group('App association files', () {
    test('both published AASA files are byte-identical', () {
      final wellKnown = File(
        'public/.well-known/apple-app-site-association',
      ).readAsStringSync();
      final root = File('public/apple-app-site-association').readAsStringSync();
      expect(wellKnown, root);

      final details =
          (((jsonDecode(wellKnown) as Map)['applinks'] as Map)['details']
                      as List)
                  .single
              as Map;
      expect(details['appID'], '2LN4253AT6.com.seolleyeon.app');
      final paths = (details['paths'] as List).cast<String>();
      expect(
        paths,
        containsAll([
          '/invite/friend',
          '/invite/team',
          '/auth/email-link',
          // The web handlers must keep opening in the browser.
          'NOT /__/auth/action/',
          'NOT /__/auth/handler/',
        ]),
      );
      // iOS evaluates the list in order: an exclusion only works when it
      // precedes nothing broader, so no catch-all may be published.
      expect(paths, isNot(contains('*')));
      expect(paths, isNot(contains('/*')));
    });

    test('both published assetlinks files are byte-identical', () {
      expect(
        File('public/.well-known/assetlinks.json').readAsStringSync(),
        File('public/assetlinks.json').readAsStringSync(),
      );
    });

    test(
      'assetlinks carries the Play app-signing certificate, not the upload key',
      () {
        final entries =
            (jsonDecode(
                      File(
                        'public/.well-known/assetlinks.json',
                      ).readAsStringSync(),
                    )
                    as List)
                .cast<Map<String, dynamic>>();
        final target = entries.single['target'] as Map<String, dynamic>;
        expect(target['package_name'], 'com.seolleyeon.app');
        final fingerprints = (target['sha256_cert_fingerprints'] as List)
            .cast<String>()
            .map((value) => value.replaceAll(':', '').toLowerCase())
            .toSet();

        // The fingerprints recorded from Play Console > App integrity live in
        // the release identity script; an installed build is signed by Play,
        // so only the app-signing certificate verifies a link.
        final identityScript = File(
          'scripts/verify_android_production_identity.py',
        ).readAsStringSync();
        String recorded(String name) => RegExp(
          '$name\\s*=\\s*\\(\\s*"([0-9a-f]{64})"',
        ).firstMatch(identityScript)!.group(1)!;

        expect(fingerprints, contains(recorded('PLAY_APP_SIGNING_SHA256')));
        expect(fingerprints, isNot(contains(recorded('PLAY_UPLOAD_SHA256'))));
      },
    );

    test('Android claims only hosts that publish assetlinks from this site', () {
      final manifest = File(
        'android/app/src/main/AndroidManifest.xml',
      ).readAsStringSync();
      final verifiedHosts =
          RegExp(
            r'<intent-filter android:autoVerify="true">[\s\S]*?</intent-filter>',
          ).allMatches(manifest).expand((filter) {
            return RegExp(
              r'android:host="([^"]+)"',
            ).allMatches(filter.group(0)!).map((match) => match.group(1)!);
          }).toSet();
      expect(verifiedHosts, isNotEmpty);
      expect(
        verifiedHosts.difference({
          'seolleyeon.com',
          'seolleyeon-final.web.app',
          'seolleyeon-final.firebaseapp.com',
        }),
        isEmpty,
      );
    });
  });
}
