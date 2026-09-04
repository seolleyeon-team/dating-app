// 블라인드 취향 미팅 repository 세션 처리 테스트

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/services/auth_service.dart';
import 'package:seolleyeon/services/storage_service.dart';

class _FakeStorageService extends StorageService {
  _FakeStorageService(this._userId);

  final String? _userId;

  // 저장소는 canonical 이름(getAppUserId)이 실제 구현이고 getKakaoUserId 는
  // 거기로 위임하는 legacy 별칭이다. repository 가 canonical 이름을 부르므로
  // 별칭만 가로채면 진짜 구현이 SharedPreferences 를 건드려 테스트가 깨진다.
  @override
  Future<String?> getAppUserId() async => _userId;
}

class _FakeAuthService extends AuthService {
  _FakeAuthService({required this.sessionAttached});

  final bool sessionAttached;
  int ensureCalls = 0;
  int kakaoTokenCalls = 0;

  @override
  Future<bool> ensureCanonicalAppSession() async {
    ensureCalls++;
    return sessionAttached;
  }

  @override
  Future<String?> getKakaoAccessTokenForFunctions() async {
    kakaoTokenCalls++;
    return null;
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  BlindMeetingRepository build({
    String? userId = 'u1',
    bool sessionAttached = true,
    _FakeAuthService? auth,
  }) {
    return BlindMeetingRepository(
      authService: auth ?? _FakeAuthService(sessionAttached: sessionAttached),
      storageService: _FakeStorageService(userId),
    );
  }

  group('세션 요구', () {
    test('로그인 정보가 없으면 로그인 필요 안내를 던진다', () {
      final repository = build(userId: null);
      expect(
        () => repository.loadMyDna(),
        throwsA(
          isA<StateError>().having((e) => e.message, 'message', '로그인이 필요해요.'),
        ),
      );
    });

    test('카카오 토큰 만료로 세션을 붙일 수 없으면 재로그인 안내를 던진다', () {
      // 원인을 알 수 없는 permission-denied 대신 재로그인 안내가 나와야 한다.
      final repository = build(sessionAttached: false);
      expect(
        () => repository.loadMyDna(),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            '로그인이 만료됐어요. 다시 로그인해주세요.',
          ),
        ),
      );
    });

    test('DNA 구독도 같은 안내를 던진다', () {
      final repository = build(sessionAttached: false);
      expect(repository.watchMyDna(), emitsError(isA<StateError>()));
    });

    test('신청 상태 구독도 같은 안내를 던진다', () {
      final repository = build(sessionAttached: false);
      expect(repository.watchMyApplication(), emitsError(isA<StateError>()));
    });

    test('세션이 붙어 있으면 매번 재확인만 하고 통과한다', () async {
      final auth = _FakeAuthService(sessionAttached: true);
      final repository = build(auth: auth);
      // Firestore 접근 전까지 세션 확인이 수행된다.
      await repository.loadMyDna().catchError((_) => null);
      expect(auth.ensureCalls, 1);
    });
  });

  group('현재 사용자', () {
    test('세션 없이도 userId는 조회할 수 있다', () async {
      final repository = build(sessionAttached: false);
      expect(await repository.currentUserId(), 'u1');
    });
  });

  group('callable payload', () {
    test('카카오 액세스 토큰을 요청하지 않는다', () async {
      // 서버가 Firebase Auth uid만 검증하므로 만료된 카카오 토큰 왕복이 없어야 한다.
      final auth = _FakeAuthService(sessionAttached: true);
      final repository = build(auth: auth);
      try {
        await repository.cancelApplication();
      } catch (_) {
        // callable 자체는 이 테스트 환경에 없다. 세션 처리만 검증한다.
      }
      expect(auth.ensureCalls, 1);
      expect(auth.kakaoTokenCalls, 0);
    });
  });
}
