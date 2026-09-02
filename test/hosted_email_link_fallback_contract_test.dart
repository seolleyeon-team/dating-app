import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final hostedPage = File('public/auth-email-link.html').readAsStringSync();

  test('hosted page recognizes primary tokens before legacy Kakao tokens', () {
    final flowBranch = hostedPage.indexOf("flow === 'primary_auth'");
    final tokenRead = hostedPage.indexOf("stage = 'read_token_doc'");
    final primaryBranch = hostedPage.indexOf("data.purpose === 'primary_auth'");
    final legacyRead = hostedPage.indexOf(
      'const kakaoUserId = data.kakaoUserId',
    );

    expect(flowBranch, isNonNegative);
    expect(tokenRead, isNonNegative);
    expect(flowBranch, lessThan(tokenRead));
    expect(primaryBranch, isNonNegative);
    expect(legacyRead, isNonNegative);
    expect(primaryBranch, lessThan(legacyRead));
  });

  test('new primary email links bypass stale hosted-page caches', () {
    final functionsIndex = File('functions/src/index.ts').readAsStringSync();

    expect(functionsIndex, contains('EMAIL_LINK_PAGE_VERSION'));
    expect(
      functionsIndex,
      contains('buildStudentVerificationContinueUrl(token, "primary_auth")'),
    );
    expect(functionsIndex, contains('url.searchParams.set("v",'));
    expect(functionsIndex, contains('url.searchParams.set("flow", flow)'));
  });

  test('hosted page offers a credential-preserving native app fallback', () {
    expect(hostedPage, contains('id="open-app"'));
    expect(hostedPage, contains('seolleyeon://auth/email-link'));
    expect(hostedPage, contains(r'${u.search}${u.hash}'));
    expect(hostedPage, contains('window.setTimeout(openInstalledApp, 100)'));

    // Live action credentials must never be rendered into the document.
    expect(hostedPage, isNot(contains('id="debug"')));
    expect(hostedPage, isNot(contains('openAppButton.href')));
  });

  test('Android accepts the hosted page custom-scheme fallback', () {
    final manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();

    expect(manifest, contains('android:scheme="seolleyeon"'));
    expect(manifest, contains('android:host="auth"'));
    expect(manifest, contains('android:pathPrefix="/email-link"'));
  });
}
