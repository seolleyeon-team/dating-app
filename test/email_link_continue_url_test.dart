import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/auth/utils/email_link_continue_url.dart';

void main() {
  test('mobile staging uses seolleyeon-final hosting domain', () {
    final url = buildStudentEmailLinkContinueUrl(
      token: 'token-123',
      isWeb: false,
      webOrigin: 'https://ignored.example',
      firebaseProjectId: 'seolleyeon-final',
    );

    expect(url, 'https://seolleyeon-final.web.app/auth/email-link?t=token-123');
  });

  test('mobile legacy project keeps existing production hosting domain', () {
    final url = buildStudentEmailLinkContinueUrl(
      token: 'token-123',
      isWeb: false,
      webOrigin: 'https://ignored.example',
      firebaseProjectId: 'seolleyeon',
    );

    expect(url, 'https://seolleyeon.web.app/auth/email-link?t=token-123');
  });

  test('web uses the current origin', () {
    final url = buildStudentEmailLinkContinueUrl(
      token: 'token-123',
      isWeb: true,
      webOrigin: 'https://preview.example',
      firebaseProjectId: 'seolleyeon-final',
    );

    expect(url, 'https://preview.example/auth/email-link?t=token-123');
  });
}
