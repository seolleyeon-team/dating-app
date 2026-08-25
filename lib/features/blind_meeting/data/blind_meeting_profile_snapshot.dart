// =============================================================================
// 3:3 블라인드 취향 미팅 — 온보딩 프로필 스냅샷 로더
// 경로: lib/features/blind_meeting/data/blind_meeting_profile_snapshot.dart
//
// 관심사·음주·흡연·MBTI는 온보딩에서 이미 받았으므로 DNA 작성 화면에서
// 다시 중복 질문하지 않고 여기서 불러온다.
// =============================================================================

import '../domain/blind_meeting_enums.dart';

/// 온보딩에서 가져온 값 묶음.
class BlindMeetingProfileSnapshot {
  final String userId;
  final String nickname;
  final String? department;
  final String? mbti;
  final List<String> interests;
  final DrinkingLevel? drinkingLevel;
  final SmokingStatus? smokingStatus;
  final bool schoolVerified;

  /// 저장된 생활권 (`onboarding.campusLifeZones`). 없으면 빈 목록.
  final List<String> campusLifeZones;
  final String? oneLineIntro;
  final DateTime? onboardingUpdatedAt;

  const BlindMeetingProfileSnapshot({
    required this.userId,
    required this.nickname,
    this.department,
    this.mbti,
    this.interests = const <String>[],
    this.drinkingLevel,
    this.smokingStatus,
    this.schoolVerified = false,
    this.campusLifeZones = const <String>[],
    this.oneLineIntro,
    this.onboardingUpdatedAt,
  });

  /// 라이프스타일 값이 비어 있어 보완 입력이 필요한지.
  bool get needsLifestyleUpdate =>
      drinkingLevel == null || smokingStatus == null;

  /// 관심사가 없어 보완 입력이 필요한지.
  bool get needsInterests => interests.isEmpty;

  /// 생활권이 계산된 적이 없어 보완 입력이 필요한지.
  ///
  /// 미팅은 실제로 만날 수 있는 생활권끼리만 성사되므로 값이 없으면
  /// 후보에서 제외된다 (fail-closed).
  bool get needsCampusLifeZone => campusLifeZones.isEmpty;

  /// 스냅샷이 오래되어 재확인이 필요한지.
  bool isStale(DateTime now, {Duration threshold = const Duration(days: 180)}) {
    final updated = onboardingUpdatedAt;
    if (updated == null) return true;
    return now.difference(updated) > threshold;
  }

  /// 공개 카드에 노출할 관심사 상위 3개.
  List<String> get topInterests => interests.take(3).toList();

  /// `users/{uid}` 문서에서 스냅샷을 만든다.
  ///
  /// [data]는 Firestore Timestamp가 DateTime으로 정규화된 맵이어야 한다.
  static BlindMeetingProfileSnapshot fromUserDoc(
    String userId,
    Map<String, dynamic> data,
  ) {
    final onboarding = data['onboarding'];
    final onboardingMap = onboarding is Map
        ? Map<String, dynamic>.from(onboarding.cast<String, dynamic>())
        : <String, dynamic>{};
    final lifestyle = onboardingMap['lifestyle'];
    final lifestyleMap = lifestyle is Map
        ? Map<String, dynamic>.from(lifestyle.cast<String, dynamic>())
        : <String, dynamic>{};

    return BlindMeetingProfileSnapshot(
      userId: userId,
      nickname: _stringOr(onboardingMap['nickname'] ?? data['nickname'], '익명'),
      department: _nullableString(
        onboardingMap['department'] ?? onboardingMap['major'],
      ),
      mbti: _nullableString(onboardingMap['mbti'])?.toUpperCase(),
      interests: _stringList(onboardingMap['interests']),
      drinkingLevel: enumFromNameOrNull(
        DrinkingLevel.values,
        lifestyleMap['drinking'],
      ),
      smokingStatus: enumFromNameOrNull(
        SmokingStatus.values,
        lifestyleMap['smoking'],
      ),
      schoolVerified: data['isStudentVerified'] == true,
      campusLifeZones: _stringList(onboardingMap['campusLifeZones']),
      oneLineIntro: _nullableString(onboardingMap['selfIntroduction']),
      onboardingUpdatedAt: _dateTime(
        data['onboardingUpdatedAt'] ?? data['updatedAt'],
      ),
    );
  }
}

String _stringOr(Object? raw, String fallback) =>
    _nullableString(raw) ?? fallback;

String? _nullableString(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

List<String> _stringList(Object? raw) {
  if (raw is! Iterable) return const <String>[];
  final seen = <String>{};
  final result = <String>[];
  for (final item in raw) {
    final text = item?.toString().trim() ?? '';
    if (text.isEmpty) continue;
    if (seen.add(text)) result.add(text);
  }
  return List<String>.unmodifiable(result);
}

DateTime? _dateTime(Object? raw) {
  if (raw is DateTime) return raw;
  if (raw is num) return DateTime.fromMillisecondsSinceEpoch(raw.toInt());
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
