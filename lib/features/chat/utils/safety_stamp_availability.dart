import 'package:cloud_firestore/cloud_firestore.dart';

class SafetyStampAvailabilityResult {
  final bool canOpen;
  final DateTime? promiseTime;
  final String message;

  const SafetyStampAvailabilityResult({
    required this.canOpen,
    required this.promiseTime,
    required this.message,
  });
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
      canOpen: false,
      promiseTime: null,
      message: '확정된 약속이 있을 때만 안전도장을 사용할 수 있어요.',
    );
  }

  final promiseStatus = promise['status']?.toString();
  final promiseTime = parsePromiseDateTime(promise['dateTime']);

  if (!isConfirmedPromiseStatus(promiseStatus)) {
    return const SafetyStampAvailabilityResult(
      canOpen: false,
      promiseTime: null,
      message: '확정된 약속에서만 안전도장을 사용할 수 있어요.',
    );
  }

  if (promiseTime == null) {
    return const SafetyStampAvailabilityResult(
      canOpen: false,
      promiseTime: null,
      message: '약속 시간이 확인되지 않아 안전도장을 열 수 없어요.',
    );
  }

  if (canOpenSafetyStamp(promiseTime, resolvedNow)) {
    return SafetyStampAvailabilityResult(
      canOpen: true,
      promiseTime: promiseTime,
      message: '지금은 안전도장을 사용할 수 있어요.',
    );
  }

  return SafetyStampAvailabilityResult(
    canOpen: false,
    promiseTime: promiseTime,
    message: '안전도장은 약속 10분 전부터 약속 후 1시간까지 사용할 수 있어요.',
  );
}
