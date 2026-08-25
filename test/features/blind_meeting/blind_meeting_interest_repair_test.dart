import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_analytics.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import 'package:seolleyeon/router/route_names.dart';

class _NoopAnalyticsSink implements BlindMeetingAnalyticsSink {
  @override
  Future<void> send(String event, Map<String, dynamic> params) async {}
}

class _IntroRepository extends BlindMeetingRepository {
  _IntroRepository(this.profiles, {this.campusLifeZoneEnforced = true});

  final List<BlindMeetingProfileSnapshot?> profiles;

  /// 서버가 정하는 rollout activation 상태. 화면은 이 값을 따르기만 한다.
  final bool campusLifeZoneEnforced;
  int profileReads = 0;
  int activationReads = 0;

  @override
  Future<bool> loadCampusLifeZoneEnforced() async {
    activationReads++;
    return campusLifeZoneEnforced;
  }

  @override
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async {
    final index = profileReads++;
    return profiles[index.clamp(0, profiles.length - 1)];
  }

  @override
  Future<BlindMeetingApplication?> loadMyApplication() async => null;
}

BlindMeetingProfileSnapshot _profile({
  required List<String> interests,
  bool schoolVerified = true,
  // 생활권도 hard eligibility 다. 기본 fixture 는 정상 사용자를 표현한다.
  List<String> campusLifeZones = const <String>['sinchon'],
}) {
  return BlindMeetingProfileSnapshot(
    userId: 'fixture-user',
    nickname: '테스터',
    interests: interests,
    schoolVerified: schoolVerified,
    campusLifeZones: campusLifeZones,
  );
}

Widget _introApp({
  required _IntroRepository repository,
  Map<String, WidgetBuilder> routes = const <String, WidgetBuilder>{},
}) {
  return MaterialApp(
    home: BlindMeetingIntroScreen(
      repository: repository,
      analytics: BlindMeetingAnalytics(sink: _NoopAnalyticsSink()),
    ),
    onGenerateRoute: (settings) {
      final builder = routes[settings.name];
      if (builder == null) return null;
      return MaterialPageRoute<void>(settings: settings, builder: builder);
    },
  );
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  });

  group('블라인드 미팅 관심사 자격 보충 진입', () {
    testWidgets('관심사가 없으면 보충 CTA를 보여준다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>[]),
      ]);

      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.textContaining('온보딩에서 관심사를 먼저 등록해주세요.'), findsOneWidget);
      expect(find.text('관심사 등록하러가기'), findsOneWidget);
    });

    testWidgets('관심사가 있으면 보충 CTA를 보여주지 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>['넷플릭스']),
      ]);

      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.text('관심사 등록하러가기'), findsNothing);
      expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    });

    testWidgets('학교 인증만 막힌 경우 관심사 보충 CTA를 보여주지 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>['넷플릭스'], schoolVerified: false),
      ]);

      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.textContaining('학교 인증을 먼저 완료해주세요.'), findsOneWidget);
      expect(find.text('관심사 등록하러가기'), findsNothing);
      expect(find.text('미팅 DNA 작성하기'), findsNothing);
    });

    testWidgets('보충 화면에서 돌아오면 Firestore 프로필을 다시 읽는다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>[]),
        _profile(interests: const <String>['넷플릭스']),
      ]);

      await tester.pumpWidget(
        _introApp(
          repository: repository,
          routes: <String, WidgetBuilder>{
            RouteNames.onboardingInterestsSelection: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('보충 완료'),
              ),
            ),
          },
        ),
      );
      await tester.pumpAndSettle();

      final repairCta = find.text('관심사 등록하러가기');
      await tester.ensureVisible(repairCta);
      await tester.tap(repairCta);
      await tester.pumpAndSettle();
      await tester.tap(find.text('보충 완료'));
      await tester.pumpAndSettle();

      expect(repository.profileReads, 2);
      expect(find.textContaining('온보딩에서 관심사를 먼저 등록해주세요.'), findsNothing);
      expect(find.text('관심사 등록하러가기'), findsNothing);
      expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    });

    testWidgets('보충 성공 결과만으로는 자격을 우회하지 않고 재조회 결과를 따른다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>[]),
        _profile(interests: const <String>[]),
      ]);

      await tester.pumpWidget(
        _introApp(
          repository: repository,
          routes: <String, WidgetBuilder>{
            RouteNames.onboardingInterestsSelection: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('보충 완료'),
              ),
            ),
          },
        ),
      );
      await tester.pumpAndSettle();

      final repairCta = find.text('관심사 등록하러가기');
      await tester.ensureVisible(repairCta);
      await tester.tap(repairCta);
      await tester.pumpAndSettle();
      await tester.tap(find.text('보충 완료'));
      await tester.pumpAndSettle();

      expect(find.textContaining('온보딩에서 관심사를 먼저 등록해주세요.'), findsOneWidget);
      expect(find.text('관심사 등록하러가기'), findsOneWidget);
      expect(find.text('미팅 DNA 작성하기'), findsNothing);
    });
  });

  group('블라인드 미팅 생활권 자격 보충 진입', () {
    testWidgets('생활권이 없으면 안내와 보충 CTA를 보여준다', (tester) async {
      final repository = _IntroRepository([
        _profile(
          interests: const <String>['넷플릭스'],
          campusLifeZones: const <String>[],
        ),
      ]);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.textContaining('생활권 설정을 먼저 완료해주세요'), findsOneWidget);
      expect(find.text('생활권 설정하러가기'), findsOneWidget);
    });

    testWidgets('생활권이 있으면 보충 CTA를 보여주지 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>['넷플릭스']),
      ]);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.text('생활권 설정하러가기'), findsNothing);
      expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    });

    testWidgets('보충 화면에서 돌아오면 Firestore 프로필을 다시 읽는다', (tester) async {
      final repository = _IntroRepository([
        _profile(
          interests: const <String>['넷플릭스'],
          campusLifeZones: const <String>[],
        ),
        _profile(interests: const <String>['넷플릭스']),
      ]);
      await tester.pumpWidget(
        _introApp(
          repository: repository,
          routes: <String, WidgetBuilder>{
            RouteNames.campusLifeZoneRepair: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('완료'),
              ),
            ),
          },
        ),
      );
      await tester.pumpAndSettle();

      final zoneCta = find.text('생활권 설정하러가기');
      await tester.ensureVisible(zoneCta);
      await tester.tap(zoneCta);
      await tester.pumpAndSettle();
      await tester.tap(find.text('완료'));
      await tester.pumpAndSettle();

      // 저장 결과가 아니라 재조회 결과로 자격을 다시 판단한다.
      expect(repository.profileReads, 2);
      expect(find.text('생활권 설정하러가기'), findsNothing);
    });
  });

  group('생활권 rollout activation', () {
    testWidgets('OFF 면 생활권이 없어도 신청을 막지 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(
          interests: const <String>['넷플릭스'],
          campusLifeZones: const <String>[],
        ),
      ], campusLifeZoneEnforced: false);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      // 차단 사유로 올리지 않는다.
      expect(find.textContaining('생활권 설정을 먼저 완료해주세요'), findsNothing);
      // 기존처럼 신청을 시작할 수 있어야 한다.
      expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
      // 다만 미리 설정하도록 안내는 한다.
      expect(find.text('생활권 설정을 완료해주세요'), findsOneWidget);
      expect(find.text('생활권 설정하러가기'), findsOneWidget);
    });

    testWidgets('OFF 면 생활권이 이미 있는 사용자에게는 안내도 하지 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(interests: const <String>['넷플릭스']),
      ], campusLifeZoneEnforced: false);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.text('생활권 설정을 완료해주세요'), findsNothing);
      expect(find.text('생활권 설정하러가기'), findsNothing);
      expect(find.text('미팅 DNA 작성하기'), findsOneWidget);
    });

    testWidgets('OFF 가 학교 인증 같은 다른 자격까지 풀어주지는 않는다', (tester) async {
      final repository = _IntroRepository([
        _profile(
          interests: const <String>['넷플릭스'],
          schoolVerified: false,
          campusLifeZones: const <String>[],
        ),
      ], campusLifeZoneEnforced: false);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.textContaining('학교 인증을 먼저 완료해주세요.'), findsOneWidget);
      expect(find.text('미팅 DNA 작성하기'), findsNothing);
    });

    testWidgets('ON 이면 같은 프로필이 차단된다', (tester) async {
      final repository = _IntroRepository([
        _profile(
          interests: const <String>['넷플릭스'],
          campusLifeZones: const <String>[],
        ),
      ], campusLifeZoneEnforced: true);
      await tester.pumpWidget(_introApp(repository: repository));
      await tester.pumpAndSettle();

      expect(find.textContaining('생활권 설정을 먼저 완료해주세요'), findsOneWidget);
      expect(find.text('미팅 DNA 작성하기'), findsNothing);
      // activation 은 화면이 추측하지 않고 서버 값을 읽어서 정한다.
      expect(repository.activationReads, greaterThan(0));
    });
  });
}
