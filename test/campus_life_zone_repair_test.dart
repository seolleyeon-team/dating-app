import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/academic_grade_options.dart';
import 'package:seolleyeon/constants/campus_life_zones.dart';
import 'package:seolleyeon/features/onboarding/screens/campus_life_zone_repair_screen.dart';
import 'package:seolleyeon/services/campus_life_zone_repair_service.dart';

/// 저장을 Firestore 대신 in-memory 문서로 흉내내되, 생활권 계산은
/// production 과 동일하게 [CampusLifeZoneResolver] 로만 한다.
/// (repair 화면이 분류 로직을 재구현하지 않는지 확인하는 것이 핵심)
class _FakeRepairService implements CampusLifeZoneRepairService {
  _FakeRepairService({Map<String, dynamic>? onboarding, this.signedIn = true})
    : _onboarding = Map<String, dynamic>.from(onboarding ?? {});

  final Map<String, dynamic> _onboarding;
  final bool signedIn;

  int repairCalls = 0;
  bool failWrite = false;

  Map<String, dynamic> get onboarding => Map.unmodifiable(_onboarding);

  /// 서버가 정하는 값. fake 는 테스트가 지정한 상태를 그대로 돌려준다.
  bool enforced = false;
  CampusLifeZoneActivation activation = CampusLifeZoneActivation.off;

  @override
  Future<CampusLifeZoneActivation> loadActivation() async => activation;

  @override
  Future<bool> isEnforcementEnabled({bool unknownAs = false}) async {
    switch (activation) {
      case CampusLifeZoneActivation.enforced:
        return true;
      case CampusLifeZoneActivation.off:
        return enforced;
      case CampusLifeZoneActivation.unknown:
        return unknownAs;
    }
  }

  @override
  Future<CampusLifeZoneStatus?> loadStatus() async {
    if (!signedIn) return null;
    final profile = {'onboarding': _onboarding};
    return CampusLifeZoneStatus(
      zones: CampusLifeZoneRepairService.zonesFromProfile(profile),
      prefill: CampusLifeZoneRepairService.prefillFrom(profile),
    );
  }

  @override
  Future<CampusLifeZoneRepairResult> repair({
    String? grade,
    String? major,
    String? department,
    bool? isRa,
  }) async {
    repairCalls += 1;
    if (!signedIn) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.notSignedIn,
      );
    }
    if (failWrite) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.nothingToSave,
      );
    }

    if (grade != null) _onboarding['grade'] = grade;
    if (major != null) _onboarding['major'] = major;
    if (department != null) _onboarding['department'] = department;
    if (isRa != null) _onboarding['isRa'] = isRa;

    // production write path 와 동일하게 기존 resolver 로만 계산한다.
    final resolved = CampusLifeZoneResolver.resolve(
      grade: _onboarding['grade']?.toString(),
      department: _onboarding['department']?.toString(),
      isRa: _onboarding['isRa'] == true,
    );
    if (resolved != null) {
      _onboarding['campusLifeZones'] = resolved.zones;
      _onboarding['campusLifeZoneLabels'] = resolved.labels;
    }

    // Firestore 재조회에 해당: 저장 결과를 다시 읽어 판정한다.
    final zones = CampusLifeZoneRepairService.zonesFromProfile({
      'onboarding': _onboarding,
    });
    if (zones.isEmpty) {
      return const CampusLifeZoneRepairResult.failure(
        CampusLifeZoneRepairError.unresolved,
      );
    }
    return CampusLifeZoneRepairResult.saved(zones);
  }
}

Future<void> _pumpRepair(
  WidgetTester tester,
  _FakeRepairService service,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => CampusLifeZoneRepairScreen(service: service),
      ),
      navigatorObservers: const [],
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String label) async {
  final finder = find.widgetWithText(ChoiceChip, label);
  await tester.scrollUntilVisible(
    finder.first,
    120,
    scrollable: find.byType(Scrollable).first,
  );
  expect(finder, findsWidgets, reason: '"$label" 선택지를 찾지 못했다');
  await tester.ensureVisible(finder.first);
  await tester.pumpAndSettle();
  await tester.tap(finder.first);
  await tester.pumpAndSettle();
}

Future<void> _submit(WidgetTester tester) async {
  final button = find.widgetWithText(ElevatedButton, '생활권 설정 완료');
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  group('생활권 rollout activation 판정', () {
    test('config 문서가 없거나 비어 있으면 OFF 다', () {
      expect(CampusLifeZoneRepairService.enforcedFromConfig(null), isFalse);
      expect(
        CampusLifeZoneRepairService.enforcedFromConfig(<String, dynamic>{}),
        isFalse,
      );
    });

    test('정확히 boolean true 일 때만 ON 이다', () {
      expect(
        CampusLifeZoneRepairService.enforcedFromConfig(<String, dynamic>{
          'campusLifeZoneEnforced': true,
        }),
        isTrue,
      );
      for (final loose in <dynamic>[false, 'true', 1, 'ON']) {
        expect(
          CampusLifeZoneRepairService.enforcedFromConfig(<String, dynamic>{
            'campusLifeZoneEnforced': loose,
          }),
          isFalse,
          reason: '느슨한 값으로 정책이 켜지면 안 된다',
        );
      }
    });

    test('config 위치가 서버와 같은 곳을 가리킨다', () {
      expect(
        CampusLifeZoneRepairService.recommendationConfigCollection,
        'recommendationConfig',
      );
      expect(CampusLifeZoneRepairService.recommendationConfigDoc, 'current');
      expect(
        CampusLifeZoneRepairService.campusLifeZoneEnforcedField,
        'campusLifeZoneEnforced',
      );
    });
  });

  group('생활권 보충 서비스', () {
    test('저장된 생활권을 canonical 경로에서 읽는다', () {
      final zones = CampusLifeZoneRepairService.zonesFromProfile({
        'onboarding': {
          'campusLifeZones': ['sinchon', 'songdo'],
        },
      });
      expect(zones, {'sinchon', 'songdo'});
    });

    test('생활권이 없으면 보충이 필요하다고 판정한다', () {
      final status = CampusLifeZoneStatus(
        zones: const <String>{},
        prefill: const CampusLifeZoneRepairPrefill(),
      );
      expect(status.needsRepair, isTrue);
    });

    test('학년·학과가 있어도 값이 없으면 추측하지 않는다', () {
      final zones = CampusLifeZoneRepairService.zonesFromProfile({
        'onboarding': {'grade': '1학년', 'department': '첨단융합공학부'},
      });
      expect(zones, isEmpty);
    });

    test('기존 값을 prefill 로 복원한다', () {
      final prefill = CampusLifeZoneRepairService.prefillFrom({
        'onboarding': {
          'grade': '2학년',
          'major': 'science',
          'department': '건축공학과',
          'isRa': true,
        },
      });
      expect(prefill.grade, '2학년');
      expect(prefill.major, 'science');
      expect(prefill.department, '건축공학과');
      expect(prefill.isRa, isTrue);
    });
  });

  group('생활권 보충 화면', () {
    testWidgets('Case A — 1학년은 송도 생활권이 저장된다', (tester) async {
      final service = _FakeRepairService();
      await _pumpRepair(tester, service);

      await _select(tester, '1학년');
      await _select(tester, '이과 계열');
      await _select(tester, '건축공학과');
      await _submit(tester);

      expect(service.onboarding['campusLifeZones'], ['songdo']);
    });

    testWidgets('Case B — 2학년 일반 학과는 신촌 생활권이 저장된다', (tester) async {
      final service = _FakeRepairService();
      await _pumpRepair(tester, service);

      await _select(tester, '3학년');
      await _select(tester, '이과 계열');
      await _select(tester, '건축공학과');
      await _submit(tester);

      expect(service.onboarding['campusLifeZones'], ['sinchon']);
    });

    testWidgets('Case C — 국제계열 2학년 이상은 신촌+송도가 모두 저장된다', (tester) async {
      final service = _FakeRepairService();
      await _pumpRepair(tester, service);

      await _select(tester, '2학년');
      await _select(tester, '문과 계열');
      await _select(tester, '언더우드학부(인문·사회)');
      await _submit(tester);

      // dual-zone 이 단일 값으로 축소되면 안 된다.
      expect(service.onboarding['campusLifeZones'], ['sinchon', 'songdo']);
    });

    testWidgets('Case D — 필수 값이 없으면 제출 자체가 막힌다', (tester) async {
      final service = _FakeRepairService();
      await _pumpRepair(tester, service);

      final button = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, '생활권 설정 완료'),
      );
      expect(button.onPressed, isNull, reason: '학년·학과 미선택 시 비활성이어야 한다');
      expect(service.repairCalls, 0);
    });

    testWidgets('Case E — 저장 실패면 성공 처리하지 않고 화면에 남는다', (tester) async {
      final service = _FakeRepairService()..failWrite = true;
      await _pumpRepair(tester, service);

      await _select(tester, '1학년');
      await _select(tester, '이과 계열');
      await _select(tester, '건축공학과');
      await _submit(tester);

      expect(find.text('생활권 설정 완료'), findsOneWidget, reason: '화면이 유지되어야 한다');
      expect(service.onboarding['campusLifeZones'], isNull);
    });

    testWidgets('Case F — 저장 전에는 기존 데이터가 바뀌지 않는다', (tester) async {
      final service = _FakeRepairService(
        onboarding: {'major': 'science'},
      );
      await _pumpRepair(tester, service);

      await _select(tester, '1학년');
      // 제출하지 않고 종료
      expect(service.repairCalls, 0);
      expect(service.onboarding['grade'], isNull);
      expect(service.onboarding['campusLifeZones'], isNull);
    });

    testWidgets('로그인 정보가 없으면 안내를 보여준다', (tester) async {
      final service = _FakeRepairService(signedIn: false);
      await _pumpRepair(tester, service);
      expect(find.textContaining('로그인 정보를 확인할 수 없어요'), findsOneWidget);
    });

    testWidgets('기존 값이 있으면 미리 선택되어 있다', (tester) async {
      final service = _FakeRepairService(
        onboarding: {'grade': '2학년', 'major': 'science', 'isRa': true},
      );
      await _pumpRepair(tester, service);

      final gradeChip = tester.widget<ChoiceChip>(
        find.widgetWithText(ChoiceChip, '2학년').first,
      );
      expect(gradeChip.selected, isTrue);
      final raSwitch = tester.widget<SwitchListTile>(
        find.byType(SwitchListTile),
      );
      expect(raSwitch.value, isTrue);
    });
  });

  group('학년 선택지 단일 소스', () {
    test('resolver 가 인식하는 문자열과 일치한다', () {
      // 옵션 라벨이 바뀌면 생활권 분류가 조용히 깨진다.
      expect(academicGradeOptions, [
        '1학년',
        '2학년',
        '3학년',
        '4학년',
        '5학년 이상',
      ]);
      for (final grade in academicGradeOptions) {
        final resolved = CampusLifeZoneResolver.resolve(
          grade: grade,
          department: '건축공학과',
          isRa: false,
        );
        expect(
          resolved?.zones,
          isNotEmpty,
          reason: '$grade 은 생활권으로 해석되어야 한다',
        );
      }
    });
  });
}
