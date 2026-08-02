// =============================================================================
// 3:3 블라인드 취향 미팅 — 공개용 프로필 스냅샷
// 경로: lib/features/blind_meeting/domain/blind_meeting_public_profile.dart
//
// 블라인드 미팅은 얼굴을 사전 공개하지 않는다. 따라서 이 스냅샷에는
// 실제 사진 URL을 담지 않고, 결정적으로 생성되는 비식별 아바타 seed만 담는다.
// 비공개 DNA(대화 성향, 음주·흡연 상세 응답)는 절대 포함하지 않는다.
// =============================================================================

/// 안전도장 이력 요약. 내부 신뢰 점수는 노출하지 않는다.
class SafetyStampSummary {
  /// 정상 완료한 미팅 수.
  final int completedMeetings;

  /// 시작 안전도장 완료 여부가 모두 채워졌는지.
  final bool allCheckinsCompleted;

  /// 종료 안전도장 완료 여부가 모두 채워졌는지.
  final bool allCheckoutsCompleted;

  const SafetyStampSummary({
    this.completedMeetings = 0,
    this.allCheckinsCompleted = false,
    this.allCheckoutsCompleted = false,
  });

  bool get hasHistory => completedMeetings > 0;

  /// 카드에 노출할 짧은 라벨. 이력이 없으면 null.
  String? get badgeLabel {
    if (!hasHistory) return null;
    if (allCheckinsCompleted && allCheckoutsCompleted) {
      return '안전도장 $completedMeetings회 모두 완료';
    }
    return '미팅 $completedMeetings회 참여';
  }

  Map<String, dynamic> toMap() => {
    'completedMeetings': completedMeetings,
    'allCheckinsCompleted': allCheckinsCompleted,
    'allCheckoutsCompleted': allCheckoutsCompleted,
  };

  static SafetyStampSummary fromMap(Object? raw) {
    if (raw is! Map) return const SafetyStampSummary();
    final completed = raw['completedMeetings'];
    return SafetyStampSummary(
      completedMeetings: completed is num ? completed.toInt() : 0,
      allCheckinsCompleted: raw['allCheckinsCompleted'] == true,
      allCheckoutsCompleted: raw['allCheckoutsCompleted'] == true,
    );
  }
}

/// 추천 결과 화면에서 다른 참가자에게 보여주는 정보 전부.
class BlindMeetingPublicProfile {
  final String userId;
  final String nickname;
  final String? department;
  final String? mbti;

  /// 최대 3개까지의 관심사.
  final List<String> topInterestIds;

  /// 비식별 실루엣 아바타 렌더링용 seed (얼굴 사진 아님).
  final String avatarSeed;

  final bool schoolVerified;
  final SafetyStampSummary safetyStampSummary;
  final String? oneLineIntro;

  const BlindMeetingPublicProfile({
    required this.userId,
    required this.nickname,
    this.department,
    this.mbti,
    this.topInterestIds = const <String>[],
    required this.avatarSeed,
    this.schoolVerified = false,
    this.safetyStampSummary = const SafetyStampSummary(),
    this.oneLineIntro,
  });

  Map<String, dynamic> toMap() => {
    'userId': userId,
    'nickname': nickname,
    'department': department,
    'mbti': mbti,
    'topInterestIds': topInterestIds,
    'avatarSeed': avatarSeed,
    'schoolVerified': schoolVerified,
    'safetyStampSummary': safetyStampSummary.toMap(),
    'oneLineIntro': oneLineIntro,
  };

  static BlindMeetingPublicProfile fromMap(Map<String, dynamic> data) {
    final userId = data['userId']?.toString() ?? '';
    return BlindMeetingPublicProfile(
      userId: userId,
      nickname: _trimmedOr(data['nickname'], '익명'),
      department: _trimmedOrNull(data['department']),
      mbti: _trimmedOrNull(data['mbti'])?.toUpperCase(),
      topInterestIds: _stringList(data['topInterestIds'], limit: 3),
      avatarSeed: _trimmedOr(data['avatarSeed'], userId),
      schoolVerified: data['schoolVerified'] == true,
      safetyStampSummary: SafetyStampSummary.fromMap(
        data['safetyStampSummary'],
      ),
      oneLineIntro: _trimmedOrNull(data['oneLineIntro']),
    );
  }
}

String _trimmedOr(Object? raw, String fallback) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String? _trimmedOrNull(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

List<String> _stringList(Object? raw, {int? limit}) {
  if (raw is! Iterable) return const <String>[];
  final result = <String>[];
  for (final item in raw) {
    final text = item?.toString().trim() ?? '';
    if (text.isEmpty) continue;
    result.add(text);
    if (limit != null && result.length >= limit) break;
  }
  return List<String>.unmodifiable(result);
}
