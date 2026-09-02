import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('successful email send releases the idempotency request id', () {
    final source = File(
      'lib/features/auth/screens/student_verification_screen.dart',
    ).readAsStringSync();
    final start = source.indexOf('Future<void> _sendEmailLink()');
    final end = source.indexOf('\n  Future<', start + 1);
    final section = source.substring(start, end < 0 ? source.length : end);

    final saveIndex = section.indexOf(
      'savePendingStudentEmailRequestId(requestId)',
    );
    final sendIndex = section.indexOf('sendPrimaryStudentEmailLink(');
    final clearIndex = section.indexOf('clearPendingStudentEmailRequestId()');

    expect(saveIndex, greaterThanOrEqualTo(0));
    expect(sendIndex, greaterThan(saveIndex));
    expect(clearIndex, greaterThan(sendIndex));
  });
}
