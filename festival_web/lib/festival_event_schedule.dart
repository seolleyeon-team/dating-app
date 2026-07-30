import 'package:cloud_firestore/cloud_firestore.dart';

/// 페스티벌 당일 타임라인 (Firestore `festivalSettings/schedule`).
class FestivalEventSchedule {
  const FestivalEventSchedule({
    required this.enabled,
    required this.profileTasteLockAt,
    required this.batchRecommendationsAt,
    required this.recommendationsRevealAt,
    this.batchCompletedAt,
    this.title,
  });

  final bool enabled;
  final DateTime profileTasteLockAt;
  final DateTime batchRecommendationsAt;
  final DateTime recommendationsRevealAt;
  final DateTime? batchCompletedAt;
  final String? title;

  static const docPath = 'festivalSettings/schedule';

  static FestivalEventSchedule? fromSnapshot(
    DocumentSnapshot<Map<String, dynamic>> snap,
  ) {
    if (!snap.exists) return null;
    final data = snap.data();
    if (data == null || data['enabled'] != true) return null;

    final lockAt = _readTimestamp(data['profileTasteLockAt']);
    final batchAt = _readTimestamp(data['batchRecommendationsAt']);
    final revealAt = _readTimestamp(data['recommendationsRevealAt']);
    if (lockAt == null || batchAt == null || revealAt == null) return null;

    return FestivalEventSchedule(
      enabled: true,
      profileTasteLockAt: lockAt,
      batchRecommendationsAt: batchAt,
      recommendationsRevealAt: revealAt,
      batchCompletedAt: _readTimestamp(data['batchCompletedAt']),
      title: data['title'] as String?,
    );
  }

  static DateTime? _readTimestamp(dynamic value) {
    if (value is Timestamp) return value.toDate();
    if (value is DateTime) return value;
    return null;
  }

  bool isProfileTasteLocked([DateTime? now]) {
    if (!enabled) return false;
    final t = (now ?? DateTime.now()).toUtc();
    return !t.isBefore(profileTasteLockAt.toUtc());
  }

  bool areRecommendationsRevealed([DateTime? now]) {
    if (!enabled) return true;
    final t = (now ?? DateTime.now()).toUtc();
    return !t.isBefore(recommendationsRevealAt.toUtc());
  }

  /// CLIP 일괄 매칭이 돌아가는 구간 (배치 시작 ~ 공개 직전).
  bool isInBatchWindow([DateTime? now]) {
    if (!enabled) return false;
    final t = (now ?? DateTime.now()).toUtc();
    return !t.isBefore(batchRecommendationsAt.toUtc()) &&
        t.isBefore(recommendationsRevealAt.toUtc());
  }

  Duration timeUntilReveal([DateTime? now]) {
    final t = (now ?? DateTime.now()).toUtc();
    final target = recommendationsRevealAt.toUtc();
    if (!t.isBefore(target)) return Duration.zero;
    return target.difference(t);
  }

  /// Firestore 시각을 KST 시계 문자열로 (표시용).
  String formatClockKst(DateTime dt) {
    final kst = dt.toUtc().add(const Duration(hours: 9));
    final h = kst.hour.toString().padLeft(2, '0');
    final m = kst.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }
}

class FestivalEventScheduleService {
  FestivalEventScheduleService(this._db);

  final FirebaseFirestore _db;

  Stream<FestivalEventSchedule?> watch() {
    return _db.doc(FestivalEventSchedule.docPath).snapshots().map(
      FestivalEventSchedule.fromSnapshot,
    );
  }

  Future<FestivalEventSchedule?> load() async {
    final snap = await _db.doc(FestivalEventSchedule.docPath).get();
    return FestivalEventSchedule.fromSnapshot(snap);
  }
}
