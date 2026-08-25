import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/ai_recommendation_service.dart';
import 'package:seolleyeon/services/campus_life_zone_repair_service.dart';
import 'package:seolleyeon/shared/utils/campus_life_zone_values.dart';
import 'package:seolleyeon/shared/utils/recommendation_eligibility.dart';

Map<String, dynamic> _profile(dynamic zones) => <String, dynamic>{
  'onboarding': <String, dynamic>{'campusLifeZones': zones},
};

Map<String, dynamic> _recDoc(String? policyState) => <String, dynamic>{
  'items': <dynamic>[],
  if (policyState != null)
    'policy': <String, dynamic>{'campusLifeZone': policyState},
};

void main() {
  group('canonical 생활권 값 검증', () {
    test('canonical 값만 통과한다', () {
      expect(CampusLifeZoneValues.readPersisted(['sinchon']), {'sinchon'});
      expect(CampusLifeZoneValues.readPersisted(['songdo']), {'songdo'});
      expect(CampusLifeZoneValues.readPersisted(['sinchon', 'songdo']), {
        'sinchon',
        'songdo',
      });
    });

    test('손상된 값은 값 전체를 무효로 본다', () {
      for (final value in <List<dynamic>>[
        ['garbage'],
        ['sinchon', 'garbage'],
        ['SINCHON'],
        ['신촌'],
        [''],
        ['sinchon', ''],
        ['sinchon', null],
        ['sinchon', 1],
        <dynamic>[],
      ]) {
        expect(
          CampusLifeZoneValues.readPersisted(value),
          isEmpty,
          reason: '$value 는 생활권으로 인정되면 안 된다',
        );
      }
    });

    test('저장 타입이 다르면 무효다 (raw string 포함)', () {
      for (final value in <dynamic>[
        'sinchon',
        123,
        null,
        true,
        {'zone': 'sinchon'},
      ]) {
        expect(
          CampusLifeZoneValues.readPersisted(value),
          isEmpty,
          reason: '$value 는 List<String> 스키마가 아니다',
        );
      }
    });
  });

  group('serving guard 가 손상된 값을 인정하지 않는다', () {
    test('같은 손상 값끼리도 추천되지 않는다', () {
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          _profile(['garbage']),
          _profile(['garbage']),
        ),
        isFalse,
      );
    });

    test('raw string 으로 저장된 프로필은 생활권이 없는 것으로 본다', () {
      expect(
        RecommendationEligibility.campusLifeZonesOf(_profile('sinchon')),
        isEmpty,
      );
      expect(
        RecommendationEligibility.passesCampusLifeZoneGate(
          enforced: true,
          viewerZones: const {'sinchon'},
          candidateZones: RecommendationEligibility.campusLifeZonesOf(
            _profile('sinchon'),
          ),
        ),
        isFalse,
      );
    });

    test('이중 생활권은 그대로 양쪽과 호환된다', () {
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          _profile(['sinchon', 'songdo']),
          _profile(['songdo']),
        ),
        isTrue,
      );
    });

    test('보충 서비스도 손상된 값을 보충 필요 상태로 본다', () {
      expect(CampusLifeZoneRepairService.hasZones(_profile(['garbage'])), isFalse);
      expect(CampusLifeZoneRepairService.hasZones(_profile('sinchon')), isFalse);
      expect(CampusLifeZoneRepairService.hasZones(_profile(['sinchon'])), isTrue);
    });
  });

  group('serving guard 의 활성화 판정 (stale 문서 포함)', () {
    setUp(CampusLifeZoneRepairService.resetEnforcedObservedForTest);

    test('Case A — 문서는 off 인데 config 가 ON 이면 강제한다', () {
      // 어제자 문서를 그대로 쓰면 cross-zone 이 노출된다.
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: 'off',
          activation: CampusLifeZoneActivation.enforced,
          enforcedObserved: false,
        ),
        isTrue,
      );
    });

    test('Case B — 문서가 enforced 면 config 조회 실패여도 강제한다', () {
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: 'enforced',
          activation: CampusLifeZoneActivation.unknown,
          enforcedObserved: false,
        ),
        isTrue,
      );
    });

    test('Case C — metadata 가 없어도 config 가 ON 이면 강제한다', () {
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: null,
          activation: CampusLifeZoneActivation.enforced,
          enforcedObserved: false,
        ),
        isTrue,
      );
    });

    test('Case D — metadata 없음 + 조회 실패는 준비 단계 기본값(미적용)', () {
      // 활성화를 한 번도 확인한 적 없는 상태다. 여기서 강제하면 준비 단계의
      // 장애가 기존 사용자 전원의 피드를 비운다.
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: null,
          activation: CampusLifeZoneActivation.unknown,
          enforcedObserved: false,
        ),
        isFalse,
      );
    });

    test('Case D+ — 활성화를 확인한 적이 있으면 조회 실패에도 유지한다', () {
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: null,
          activation: CampusLifeZoneActivation.unknown,
          enforcedObserved: true,
        ),
        isTrue,
      );
    });

    test('명시적 OFF 는 강제하지 않는다 (준비 단계 정상 동작)', () {
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: null,
          activation: CampusLifeZoneActivation.off,
          enforcedObserved: false,
        ),
        isFalse,
      );
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: 'off',
          activation: CampusLifeZoneActivation.off,
          enforcedObserved: false,
        ),
        isFalse,
      );
    });

    test('한 번 확인된 활성화는 OFF config 로만 내려간다', () {
      // 조회에 성공해 명시적으로 off 를 받으면 rollback 이 즉시 반영된다.
      expect(
        AiRecommendationService.shouldEnforceCampusLifeZone(
          documentPolicyState: null,
          activation: CampusLifeZoneActivation.off,
          enforcedObserved: true,
        ),
        isFalse,
        reason: 'rollback 은 재배포 없이 즉시 반영돼야 한다',
      );
    });

    test('문서 metadata 를 읽는 규칙', () {
      expect(AiRecommendationService.policyStateOf(_recDoc('enforced')), 'enforced');
      expect(AiRecommendationService.policyStateOf(_recDoc('off')), 'off');
      expect(AiRecommendationService.policyStateOf(_recDoc(null)), isNull);
      expect(AiRecommendationService.policyStateOf(null), isNull);
      expect(
        AiRecommendationService.policyStateOf(<String, dynamic>{'policy': 'off'}),
        isNull,
      );
    });
  });

  group('activation 판정 규칙', () {
    test('정확히 boolean true 일 때만 ON 이다', () {
      expect(
        CampusLifeZoneRepairService.enforcedFromConfig(<String, dynamic>{
          'campusLifeZoneEnforced': true,
        }),
        isTrue,
      );
      for (final loose in <dynamic>['true', 1, 'ON', false, null]) {
        expect(
          CampusLifeZoneRepairService.enforcedFromConfig(<String, dynamic>{
            'campusLifeZoneEnforced': loose,
          }),
          isFalse,
        );
      }
    });
  });
}
