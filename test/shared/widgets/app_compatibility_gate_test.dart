import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/core/compatibility/app_compatibility.dart';
import 'package:seolleyeon/core/compatibility/app_compatibility_service.dart';
import 'package:seolleyeon/shared/widgets/app_compatibility_gate.dart';

/// 업데이트 게이트가 실제로 화면을 막는지, 그리고 우회 경로가 없는지.
///
/// 게이트는 `MaterialApp.builder` 에 놓여 Navigator 위에 앉는다. 그래서
/// 라우트를 어떤 방식으로 밀어넣든 게이트 아래에 깔린다는 것이 이 설계의
/// 핵심 주장이고, 여기서 검증하는 것이 그 주장이다.
void main() {
  const homeText = '홈 화면';
  const secretText = '알림으로 열린 화면';

  final navigatorKey = GlobalKey<NavigatorState>();

  AppCompatibilityService gateService({
    required int minimumBuild,
    int buildNumber = 14,
    Set<String> required = const {},
    String? storeUrl = 'https://play.google.com/store/apps/details?id=x',
  }) {
    return AppCompatibilityService(
      fetchPolicy: (_) async => {
        'android': {
          'minimumSupportedBuild': minimumBuild,
          'storeUrl': storeUrl,
        },
        'requiredCapabilities': required.toList(),
      },
      readBuildNumber: () async => buildNumber,
      flavor: 'production',
      platform: CompatibilityPlatform.android,
    );
  }

  Widget app(AppCompatibilityService service) {
    return MaterialApp(
      navigatorKey: navigatorKey,
      routes: {
        '/': (_) => const Scaffold(body: Text(homeText)),
        '/deep': (_) => const Scaffold(body: Text(secretText)),
      },
      builder: (context, child) => AppCompatibilityGate(
        service: service,
        child: child ?? const SizedBox.shrink(),
      ),
    );
  }

  testWidgets('지원되는 빌드는 앱을 그대로 쓴다', (tester) async {
    await tester.pumpWidget(app(gateService(minimumBuild: 10)));
    await tester.pumpAndSettle();

    expect(find.text(homeText), findsOneWidget);
    expect(find.text('업데이트가 필요해요'), findsNothing);
  });

  testWidgets('권장 업데이트는 앱을 막지 않는다', (tester) async {
    await tester.pumpWidget(
      app(gateService(minimumBuild: 10, buildNumber: 12)),
    );
    await tester.pumpAndSettle();

    expect(find.text(homeText), findsOneWidget);
    expect(find.text('업데이트가 필요해요'), findsNothing);
  });

  testWidgets('최소 미만이면 업데이트 화면이 덮는다', (tester) async {
    await tester.pumpWidget(app(gateService(minimumBuild: 20)));
    await tester.pumpAndSettle();

    expect(find.text('업데이트가 필요해요'), findsOneWidget);
    expect(find.text('업데이트하기'), findsOneWidget);
    expect(find.text('다시 확인'), findsOneWidget);
  });

  testWidgets('capability 가 없으면 빌드가 최신이어도 덮는다', (tester) async {
    await tester.pumpWidget(
      app(
        gateService(
          minimumBuild: 0,
          buildNumber: 9999,
          required: const {'somethingThisBuildLacks'},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('업데이트가 필요해요'), findsOneWidget);
  });

  testWidgets('스토어 주소를 모르면 눌러도 소용없는 버튼을 띄우지 않는다', (tester) async {
    await tester.pumpWidget(app(gateService(minimumBuild: 20, storeUrl: null)));
    await tester.pumpAndSettle();

    expect(find.text('업데이트하기'), findsNothing);
    expect(find.textContaining('스토어에서 설레연을 검색'), findsOneWidget);
  });

  group('우회 경로', () {
    testWidgets('딥링크로 라우트를 밀어넣어도 게이트가 덮고 있다', (tester) async {
      await tester.pumpWidget(app(gateService(minimumBuild: 20)));
      await tester.pumpAndSettle();

      // 딥링크 핸들러가 하는 일과 같다.
      navigatorKey.currentState!.pushNamed('/deep');
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsOneWidget);
      // 라우트는 아래에 깔려 있어도 사용자에게 닿지 않아야 한다.
      expect(_isVisiblyOnTop(tester, secretText), isFalse);
    });

    testWidgets('푸시 알림 경로도 게이트를 뚫지 못한다', (tester) async {
      await tester.pumpWidget(app(gateService(minimumBuild: 20)));
      await tester.pumpAndSettle();

      // PushNotificationService 가 실제로 쓰는 형태.
      navigatorKey.currentState!.pushNamedAndRemoveUntil(
        '/deep',
        (route) => false,
      );
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsOneWidget);
      expect(_isVisiblyOnTop(tester, secretText), isFalse);
    });

    testWidgets('아래 라우트를 전부 pop 해도 게이트는 남는다', (tester) async {
      await tester.pumpWidget(app(gateService(minimumBuild: 20)));
      await tester.pumpAndSettle();

      navigatorKey.currentState!.pushNamed('/deep');
      await tester.pumpAndSettle();
      navigatorKey.currentState!.pop();
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsOneWidget);
    });

    testWidgets('게이트 화면이 아래 화면의 탭을 먹는다', (tester) async {
      var homeTapped = false;
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => AppCompatibilityGate(
            service: gateService(minimumBuild: 20),
            child: child ?? const SizedBox.shrink(),
          ),
          home: Scaffold(
            body: GestureDetector(
              onTap: () => homeTapped = true,
              child: const SizedBox.expand(child: Text(homeText)),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tapAt(const Offset(20, 20));
      await tester.pumpAndSettle();

      expect(homeTapped, isFalse);
    });
  });

  group('복귀 재확인', () {
    testWidgets('스토어에 다녀와 업데이트하면 게이트가 풀린다', (tester) async {
      var currentBuild = 14;
      final service = AppCompatibilityService(
        fetchPolicy: (_) async => const {
          'android': {'minimumSupportedBuild': 20},
        },
        readBuildNumber: () async => currentBuild,
        flavor: 'production',
        platform: CompatibilityPlatform.android,
      );

      await tester.pumpWidget(app(service));
      await tester.pumpAndSettle();
      expect(find.text('업데이트가 필요해요'), findsOneWidget);

      // 사용자가 업데이트하고 돌아온다. 여기서 다시 보지 않으면 업데이트를
      // 마치고도 화면이 그대로 막혀 있다.
      currentBuild = 25;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsNothing);
      expect(find.text(homeText), findsOneWidget);
    });

    testWidgets('"다시 확인" 이 판정을 새로 한다', (tester) async {
      var attempt = 0;
      final service = AppCompatibilityService(
        fetchPolicy: (_) async {
          attempt += 1;
          return {
            'android': {'minimumSupportedBuild': attempt == 1 ? 20 : 0},
          };
        },
        readBuildNumber: () async => 14,
        flavor: 'production',
        platform: CompatibilityPlatform.android,
      );

      await tester.pumpWidget(app(service));
      await tester.pumpAndSettle();
      expect(find.text('업데이트가 필요해요'), findsOneWidget);

      await tester.tap(find.text('다시 확인'));
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsNothing);
    });
  });

  group('정책을 못 읽었을 때', () {
    testWidgets('네트워크 실패가 앱을 잠그지 않는다', (tester) async {
      final service = AppCompatibilityService(
        fetchPolicy: (_) async => throw StateError('offline'),
        readBuildNumber: () async => 14,
        flavor: 'production',
        platform: CompatibilityPlatform.android,
      );

      await tester.pumpWidget(app(service));
      await tester.pumpAndSettle();

      expect(find.text('업데이트가 필요해요'), findsNothing);
      expect(find.text(homeText), findsOneWidget);
    });

    testWidgets('판정이 끝나기 전에도 앱이 멈추지 않는다', (tester) async {
      // 정책을 읽는 동안 화면을 막으면 오프라인 사용자가 타임아웃만큼
      // 스피너를 본다. UX 게이트가 실제 사용을 지연시키면 앞뒤가 안 맞는다.
      final service = AppCompatibilityService(
        fetchPolicy: (_) => Future.delayed(
          const Duration(seconds: 3),
          () => const {
            'android': {'minimumSupportedBuild': 0},
          },
        ),
        readBuildNumber: () async => 14,
        flavor: 'production',
        platform: CompatibilityPlatform.android,
      );

      await tester.pumpWidget(app(service));
      await tester.pump();

      expect(find.text(homeText), findsOneWidget);
      await tester.pumpAndSettle(const Duration(seconds: 4));
    });
  });

  group('로그아웃 예외 경로', () {
    testWidgets('막힌 상태에서도 로그아웃은 할 수 있다', (tester) async {
      var signedOut = false;
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => AppCompatibilityGate(
            service: gateService(minimumBuild: 20),
            onSignOut: () async => signedOut = true,
            child: child ?? const SizedBox.shrink(),
          ),
          home: const Scaffold(body: Text(homeText)),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('로그아웃'));
      await tester.pumpAndSettle();

      expect(signedOut, isTrue);
    });

    testWidgets('로그아웃 경로가 없으면 버튼도 없다', (tester) async {
      await tester.pumpWidget(app(gateService(minimumBuild: 20)));
      await tester.pumpAndSettle();

      expect(find.text('로그아웃'), findsNothing);
    });
  });
}

/// 해당 텍스트가 사용자에게 실제로 보이는 최상단인지.
///
/// `find.text` 는 게이트 아래 깔린 라우트도 찾아낸다. 라우트가 존재한다는
/// 사실이 아니라 그것이 사용자에게 닿는지를 봐야 한다.
bool _isVisiblyOnTop(WidgetTester tester, String text) {
  final finder = find.text(text);
  if (finder.evaluate().isEmpty) return false;
  final target = tester.getCenter(finder.first);
  final hit = tester.hitTestOnBinding(target);
  return hit.path.any(
    (entry) => entry.target is RenderBox && _rendersText(entry.target, text),
  );
}

bool _rendersText(HitTestTarget target, String text) {
  if (target is! RenderParagraph) return false;
  return target.text.toPlainText().contains(text);
}
