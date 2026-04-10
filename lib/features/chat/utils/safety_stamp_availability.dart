import 'package:cloud_firestore/cloud_firestore.dart';

enum SafetyStampPhase { meetup, goodbye, completed }

class SafetyStampAvailabilityResult {
  final bool isVisible;
  final bool canOpen;
  final DateTime? promiseTime;
  final String message;
  final SafetyStampPhase? phase;

  const SafetyStampAvailabilityResult({
    required this.isVisible,
    required this.canOpen,
    required this.promiseTime,
    required this.message,
    required this.phase,
  });
}

Set<String> _readStampUserIds(Map<String, dynamic>? raw, String key) {
  final values = (raw?[key] as List?)
          ?.map((e) => e.toString())
          .where((e) => e.isNotEmpty)
          .toSet() ??
      <String>{};
  return values;
}

SafetyStampPhase deriveSafetyStampPhase(Map<String, dynamic>? promise) {
  if (promise == null) return SafetyStampPhase.meetup;

  final safetyStampRaw = promise['safetyStamp'];
  final safetyStamp = safetyStampRaw is Map
      ? Map<String, dynamic>.from(safetyStampRaw)
      : const <String, dynamic>{};

  final meetupStampedUserIds = _readStampUserIds(
    safetyStamp,
    'meetupStampedUserIds',
  );
  final legacyStampedUserIds = _readStampUserIds(safetyStamp, 'stampedUserIds');
  final effectiveMeetupStampedUserIds = meetupStampedUserIds.isNotEmpty
      ? meetupStampedUserIds
      : legacyStampedUserIds;
  final goodbyeStampedUserIds = _readStampUserIds(
    safetyStamp,
    'goodbyeStampedUserIds',
  );

  final participantIds = (promise['participantIds'] as List?)
          ?.map((e) => e.toString())
          .where((e) => e.isNotEmpty)
          .toSet() ??
      <String>{};
  final expectedParticipantCount = participantIds.length >= 2
      ? participantIds.length
      : 2;

  if (participantIds.length >= 2 &&
      effectiveMeetupStampedUserIds.containsAll(participantIds)) {
    if (goodbyeStampedUserIds.containsAll(participantIds)) {
      return SafetyStampPhase.completed;
    }
    return SafetyStampPhase.goodbye;
  }

  if (effectiveMeetupStampedUserIds.length >= expectedParticipantCount) {
    if (goodbyeStampedUserIds.length >= expectedParticipantCount) {
      return SafetyStampPhase.completed;
    }
    return SafetyStampPhase.goodbye;
  }

  return SafetyStampPhase.meetup;
}

DateTime? parsePromiseDateTime(dynamic raw) {
  if (raw == null) return null;
  if (raw is Timestamp) return raw.toDate().toLocal();
  if (raw is DateTime) return raw.toLocal();
  if (raw is int) {
    return DateTime.fromMillisecondsSinceEpoch(raw).toLocal();
  }
  if (raw is String) {
    final parsed = DateTime.tryParse(raw);
    return parsed?.toLocal();
  }
  return null;
}

bool isConfirmedPromiseStatus(String? status) {
  return (status ?? '').trim().toLowerCase() == 'confirmed';
}

bool isOpenableSafetyStampStatus(String? status) {
  final normalized = (status ?? '').trim().toLowerCase();
  return normalized == 'confirmed' || normalized == 'in_progress';
}

bool canOpenSafetyStamp(DateTime promiseTime, DateTime now) {
  final openAt = promiseTime.subtract(const Duration(minutes: 10));
  final closeAt = promiseTime.add(const Duration(hours: 1));

  return !now.isBefore(openAt) && !now.isAfter(closeAt);
}

SafetyStampAvailabilityResult evaluateSafetyStampAvailability(
  Map<String, dynamic>? promise, {
  DateTime? now,
}) {
  final resolvedNow = (now ?? DateTime.now()).toLocal();

  if (promise == null) {
    return const SafetyStampAvailabilityResult(
      isVisible: false,
      canOpen: false,
      promiseTime: null,
      message: '확정된 약속이 있을 때만 안전도장을 사용할 수 있어요.',
      phase: null,
    );
  }

  final promiseStatus = promise['status']?.toString();
  final promiseTime = parsePromiseDateTime(promise['dateTime']);
  final phase = deriveSafetyStampPhase(promise);

  if (promiseTime == null) {
    return const SafetyStampAvailabilityResult(
      isVisible: false,
      canOpen: false,
      promiseTime: null,
      message: '약속 시간이 확인되지 않아 안전도장을 열 수 없어요.',
      phase: null,
    );
  }

  final closeAt = promiseTime.add(const Duration(hours: 1));

  if (phase == SafetyStampPhase.completed || resolvedNow.isAfter(closeAt)) {
    return const SafetyStampAvailabilityResult(
      isVisible: false,
      canOpen: false,
      promiseTime: null,
      message: '',
      phase: SafetyStampPhase.completed,
    );
  }

  final canOpen = isOpenableSafetyStampStatus(promiseStatus) &&
      canOpenSafetyStamp(promiseTime, resolvedNow);

  return SafetyStampAvailabilityResult(
    isVisible: true,
    canOpen: canOpen,
    promiseTime: promiseTime,
    message: canOpen
        ? (phase == SafetyStampPhase.goodbye
            ? '상대와 헤어질 때 안전도장 누르기!'
            : '상대와 만났다면 안전도장을 눌러 만남을 기록해보아요.')
        : (isOpenableSafetyStampStatus(promiseStatus)
            ? '안전도장은 약속 10분 전부터 약속 후 1시간까지 사용할 수 있어요.'
            : '확정된 약속에서만 안전도장을 사용할 수 있어요.'),
    phase: phase,
  );
}
