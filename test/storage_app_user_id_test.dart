import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/storage_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The canonical appUserId cache reuses the historical `kakao_user_id`
/// preference key so existing installs keep their identity, and the pre-auth
/// pending email keys are global (no user namespace exists before login).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('saveAppUserId writes the legacy kakao_user_id pref key', () async {
    final storage = StorageService();
    await storage.saveAppUserId('12345');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('kakao_user_id'), '12345');
    expect(await storage.getAppUserId(), '12345');
  });

  test('legacy install compatibility: an existing kakao_user_id value is '
      'readable through the new appUserId API', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'kakao_user_id': 'legacy-kakao-9999',
    });

    final storage = StorageService();
    expect(await storage.getAppUserId(), 'legacy-kakao-9999');
    // Deprecated aliases stay wired to the same key.
    expect(await storage.getKakaoUserId(), 'legacy-kakao-9999');
  });

  test('legacy save/clear aliases delegate to the canonical key', () async {
    final storage = StorageService();
    await storage.saveKakaoUserId('alias-1');
    expect(await storage.getAppUserId(), 'alias-1');

    await storage.clearKakaoUserId();
    expect(await storage.getAppUserId(), isNull);

    await storage.saveAppUserId('alias-2');
    await storage.clearAppUserId();
    expect(await storage.getKakaoUserId(), isNull);
  });

  test('pending student email keys are global and round-trip', () async {
    final storage = StorageService();
    await storage.savePendingStudentEmail('person@yonsei.ac.kr');
    await storage.savePendingStudentEmailRequestId('req-123');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('pending_student_email'), 'person@yonsei.ac.kr');
    expect(prefs.getString('pending_student_email_request_id'), 'req-123');

    expect(await storage.getPendingStudentEmail(), 'person@yonsei.ac.kr');
    expect(await storage.getPendingStudentEmailRequestId(), 'req-123');

    await storage.clearPendingStudentEmail();
    await storage.clearPendingStudentEmailRequestId();
    expect(await storage.getPendingStudentEmail(), isNull);
    expect(await storage.getPendingStudentEmailRequestId(), isNull);
  });

  test(
    'clearUserScopedSession wipes identity and pending email keys',
    () async {
      final storage = StorageService();
      await storage.saveAppUserId('u-1');
      await storage.savePendingStudentEmail('person@yonsei.ac.kr');
      await storage.savePendingStudentEmailRequestId('req-9');
      await storage.saveStudentEmail('u-1', 'person@yonsei.ac.kr');

      await storage.clearUserScopedSession('u-1');

      expect(await storage.getAppUserId(), isNull);
      expect(await storage.getPendingStudentEmail(), isNull);
      expect(await storage.getPendingStudentEmailRequestId(), isNull);
      expect(await storage.getStudentEmail('u-1'), isNull);
    },
  );

  test('per-user student email keys stay namespaced by appUserId', () async {
    final storage = StorageService();
    await storage.saveStudentEmail('user-a', 'a@yonsei.ac.kr');
    await storage.saveStudentEmail('user-b', 'b@yonsei.ac.kr');

    expect(await storage.getStudentEmail('user-a'), 'a@yonsei.ac.kr');
    expect(await storage.getStudentEmail('user-b'), 'b@yonsei.ac.kr');
  });
}
