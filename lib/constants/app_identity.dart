/// 플랫폼별 앱 식별자.
///
/// Android 는 flavor 마다 applicationId 가 다르다.
///
///   production : com.seolleyeon.app   — Google Play 에 등록된 실제 앱
///   staging    : com.yonsei.dating    — 개발/검증용, Play 에 올리지 않는다
///
/// 이메일 링크(ActionCodeSettings)나 딥링크처럼 "이 기기에 설치된 앱"을
/// 가리켜야 하는 값은 실행 중인 빌드의 패키지와 일치해야 한다. 상수로 박아두면
/// production 빌드가 staging 패키지를 가리켜 링크가 앱을 열지 못한다.
///
/// iOS Bundle ID 는 Android 패키지와 별개 식별자이며 이 마이그레이션에서
/// 바뀌지 않는다.
class AppIdentity {
  const AppIdentity._();

  /// `--flavor` 로 빌드하면 Flutter 가 넣어주는 값.
  static const String flavor = String.fromEnvironment('FLUTTER_APP_FLAVOR');

  static const String productionAndroidPackage = 'com.seolleyeon.app';
  static const String stagingAndroidPackage = 'com.yonsei.dating';

  /// 실행 중인 빌드의 Android 패키지.
  ///
  /// flavor 를 알 수 없는 빌드(예: 테스트)는 production 을 가정한다. 잘못
  /// 짚었을 때 staging 을 가리키는 쪽이 더 위험하기 때문이다 — 실제 사용자에게
  /// 나가는 링크가 설치되지 않은 패키지를 열려고 하게 된다.
  static String get androidPackage =>
      flavor == 'staging' ? stagingAndroidPackage : productionAndroidPackage;

  /// iOS 번들 ID (Android 패키지와 별개, 변경되지 않는다).
  static const String iosBundleId = 'com.yonsei.dating';

  static bool get isStaging => flavor == 'staging';
}
