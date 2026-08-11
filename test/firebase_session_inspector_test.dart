import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/firebase_session_inspector.dart';

void main() {
  const inspector = FirebaseSessionInspector();

  test('no Firebase user is classified without loading token claims', () async {
    var loadCount = 0;

    final result = await inspector.inspect(
      expectedKakaoUserId: 'kakao-1',
      currentUid: null,
      loadClaims: (forceRefresh) async {
        loadCount++;
        return <String, dynamic>{};
      },
    );

    expect(result.state, FirebaseSessionIdentityState.noSession);
    expect(loadCount, 0);
  });

  test('matching Firebase UID is accepted without forced token refresh', () async {
    var loadCount = 0;

    final result = await inspector.inspect(
      expectedKakaoUserId: 'kakao-1',
      currentUid: 'kakao-1',
      loadClaims: (forceRefresh) async {
        loadCount++;
        return <String, dynamic>{};
      },
    );

    expect(result.state, FirebaseSessionIdentityState.matching);
    expect(loadCount, 0);
  });

  test('matching kakaoUserId claim is accepted for a legacy UID', () async {
    var forceRefreshValue = false;

    final result = await inspector.inspect(
      expectedKakaoUserId: 'kakao-1',
      currentUid: 'legacy-firebase-uid',
      loadClaims: (forceRefresh) async {
        forceRefreshValue = forceRefresh;
        return <String, dynamic>{'kakaoUserId': ' kakao-1 '};
      },
    );

    expect(result.state, FirebaseSessionIdentityState.matching);
    expect(forceRefreshValue, isTrue);
  });

  test('different UID and claim are classified as an actual mismatch', () async {
    final result = await inspector.inspect(
      expectedKakaoUserId: 'kakao-1',
      currentUid: 'other-user',
      loadClaims: (forceRefresh) async => <String, dynamic>{
        'kakaoUserId': 'other-kakao',
      },
    );

    expect(result.state, FirebaseSessionIdentityState.mismatched);
  });

  test('token inspection errors are not classified as identity mismatch', () async {
    final result = await inspector.inspect(
      expectedKakaoUserId: 'kakao-1',
      currentUid: 'other-user',
      loadClaims: (forceRefresh) async {
        throw StateError('temporary token refresh failure');
      },
    );

    expect(result.state, FirebaseSessionIdentityState.inspectionFailed);
  });
}
