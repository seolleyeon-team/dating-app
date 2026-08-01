import 'package:cloud_firestore/cloud_firestore.dart';

import 'festival_recommendation_models.dart';
import 'festival_taste_affinity.dart';
import 'festival_vector_math.dart';

class FestivalRecommendationSlot {
  final String ticketId;
  final int matchPercent;
  final double score;
  final String source;

  const FestivalRecommendationSlot({
    required this.ticketId,
    required this.matchPercent,
    required this.score,
    required this.source,
  });
}

class FestivalRecommendationResult {
  final String currentGender;
  final String targetGender;
  final int availableCount;
  final List<FestivalRecommendationSlot?> slots;

  const FestivalRecommendationResult({
    required this.currentGender,
    required this.targetGender,
    required this.availableCount,
    required this.slots,
  });
}

/// 웹용 CLIP 스타일 추천 엔진 (배치 `festivalModelRecs` 미존재 시 라이브 계산).
class FestivalRecommendationEngine {
  FestivalRecommendationEngine(this._db);

  final FirebaseFirestore _db;

  String kstDateKey([DateTime? now]) {
    final kst = (now ?? DateTime.now()).toUtc().add(const Duration(hours: 9));
    final y = kst.year.toString();
    final m = kst.month.toString().padLeft(2, '0');
    final d = kst.day.toString().padLeft(2, '0');
    return '$y$m$d';
  }

  Future<FestivalRecommendationResult> loadRecommendations({
    required String ticketId,
    required String currentGender,
  }) async {
    final targetGender = currentGender == '남성' ? '여성' : '남성';
    final stored = await _loadStoredRecs(ticketId);
    if (stored.isNotEmpty) {
      return _resultFromRanked(
        ticketId: ticketId,
        currentGender: currentGender,
        targetGender: targetGender,
        ranked: stored,
      );
    }

    return generateLive(
      ticketId: ticketId,
      currentGender: currentGender,
      targetGender: targetGender,
    );
  }

  Future<List<FestivalRankedCandidate>> _loadStoredRecs(String ticketId) async {
    final todayKey = kstDateKey();
    final yesterdayKey = kstDateKey(
      DateTime.now().subtract(const Duration(days: 1)),
    );

    for (final dateKey in [todayKey, yesterdayKey]) {
      for (final source in ['rrf', 'clip']) {
        final snap = await _db
            .collection('festivalModelRecs')
            .doc(ticketId)
            .collection('daily')
            .doc(dateKey)
            .collection('sources')
            .doc(source)
            .get();
        if (!snap.exists) continue;
        final data = snap.data();
        if (data?['status'] != 'ready') continue;
        final items = data?['items'];
        if (items is! List || items.isEmpty) continue;

        final ranked = <FestivalRankedCandidate>[];
        for (final raw in items) {
          if (raw is! Map) continue;
          final candidateId =
              (raw['ticketId'] as String?) ?? (raw['uid'] as String?) ?? '';
          if (candidateId.isEmpty) continue;
          ranked.add(
            FestivalRankedCandidate(
              ticketId: candidateId,
              score: (raw['score'] as num?)?.toDouble() ?? 0,
              rank: (raw['rank'] as num?)?.toInt() ?? ranked.length + 1,
              source: source,
            ),
          );
        }
        ranked.sort((a, b) => a.rank.compareTo(b.rank));
        if (ranked.isNotEmpty) return ranked.take(12).toList();
      }
    }
    return const [];
  }

  Future<FestivalRecommendationResult> generateLive({
    required String ticketId,
    required String currentGender,
    required String targetGender,
  }) async {
    final ticketSnap = await _db
        .collection('festivalTickets')
        .doc(ticketId)
        .get();
    final ticketData = ticketSnap.data() ?? <String, dynamic>{};

    var preference = FestivalPreferenceVector.fromMap(
      ticketData['preferenceVector'] as Map<String, dynamic>?,
    );

    if (!preference.isValid) {
      final builder = FestivalTasteAffinityBuilder(_db);
      final built = await builder.buildForTicket(ticketId);
      preference = built.preferenceVector ?? preference;
      if (built.affinities.isNotEmpty || built.preferenceVector != null) {
        await builder.persistForTicket(
          ticketId,
          affinities: built.affinities,
          preferenceVector: built.preferenceVector,
        );
      }
    }

    final selfEmbedding = await _loadProfileEmbedding(ticketId);
    final prefVector = _resolvePreferenceVector(
      preference: preference,
      selfEmbedding: selfEmbedding,
    );

    final candidatesSnap = await _db
        .collection('festivalProfiles')
        .where('gender', isEqualTo: targetGender)
        .get();

    final scored = <({String ticketId, double score})>[];
    for (final doc in candidatesSnap.docs) {
      if (doc.id == ticketId) continue;
      final embedding = await _loadProfileEmbedding(doc.id);
      if (embedding == null || prefVector == null) {
        scored.add((
          ticketId: doc.id,
          score: _heuristicScore(ticketData, doc.data()),
        ));
        continue;
      }
      final cosine = FestivalVectorMath.cosineSimilarity(
        prefVector,
        embedding,
      ).clamp(0.0, 1.0);
      const faceBase = 0.15;
      final score = faceBase + (1 - faceBase) * cosine;
      scored.add((ticketId: doc.id, score: score));
    }

    scored.sort((a, b) => b.score.compareTo(a.score));
    final ranked = <FestivalRankedCandidate>[
      for (var i = 0; i < scored.length && i < 12; i++)
        FestivalRankedCandidate(
          ticketId: scored[i].ticketId,
          score: scored[i].score,
          rank: i + 1,
          source: 'clip_live',
        ),
    ];

    return _resultFromRanked(
      ticketId: ticketId,
      currentGender: currentGender,
      targetGender: targetGender,
      ranked: ranked,
      availableCount: candidatesSnap.docs.length - 1,
    );
  }

  Future<FestivalRecommendationResult> _resultFromRanked({
    required String ticketId,
    required String currentGender,
    required String targetGender,
    required List<FestivalRankedCandidate> ranked,
    int? availableCount,
  }) async {
    final slots = <FestivalRecommendationSlot?>[];
    for (final candidate in ranked) {
      if (candidate.ticketId == ticketId) continue;
      final snap = await _db
          .collection('festivalProfiles')
          .doc(candidate.ticketId)
          .get();
      if (!snap.exists) continue;
      final gender = snap.data()?['gender'] as String?;
      if (gender != targetGender) continue;

      final matchPercent = (72 + (candidate.score.clamp(-1.0, 1.0) + 1) * 13)
          .round()
          .clamp(72, 97);
      slots.add(
        FestivalRecommendationSlot(
          ticketId: candidate.ticketId,
          matchPercent: matchPercent,
          score: candidate.score,
          source: candidate.source,
        ),
      );
      if (slots.length >= 3) break;
    }

    while (slots.length < 3) {
      slots.add(null);
    }

    return FestivalRecommendationResult(
      currentGender: currentGender,
      targetGender: targetGender,
      availableCount: availableCount ?? ranked.length,
      slots: slots,
    );
  }

  List<double>? _resolvePreferenceVector({
    required FestivalPreferenceVector preference,
    required List<double>? selfEmbedding,
  }) {
    if (preference.isValid &&
        selfEmbedding != null &&
        selfEmbedding.isNotEmpty) {
      final confidence = preference.confidence.clamp(0.0, 1.0);
      final blended = List<double>.generate(preference.vector.length, (index) {
        final signal = preference.vector[index];
        final self = index < selfEmbedding.length ? selfEmbedding[index] : 0.0;
        return (confidence * signal) + ((1 - confidence) * self);
      });
      return FestivalVectorMath.l2Normalize(blended);
    }
    if (preference.isValid) return preference.vector;
    return selfEmbedding;
  }

  double _heuristicScore(
    Map<String, dynamic> viewerData,
    Map<String, dynamic>? candidateData,
  ) {
    if (candidateData == null) return 0.15;
    // Base 0.50 (0.35 + freed 0.15 from removed dept/selectivity/hash heuristics)
    var score = 0.5;
    if (viewerData['mbti'] == candidateData['mbti']) score += 0.12;
    final viewerAge = viewerData['age'];
    final candidateAge = candidateData['age'];
    if (viewerAge is int && candidateAge is int) {
      final gap = (viewerAge - candidateAge).abs();
      score += (gap <= 2
          ? 0.15
          : gap <= 4
          ? 0.08
          : 0);
    }
    return score.clamp(0.0, 1.0);
  }

  Future<List<double>?> _loadProfileEmbedding(String ticketId) async {
    final snap = await _db
        .collection('festivalProfileEmbeddings')
        .doc(ticketId)
        .get();
    if (!snap.exists) return null;
    final raw = snap.data()?['vector'];
    if (raw is! List || raw.isEmpty) return null;
    return raw
        .map((value) => (value as num).toDouble())
        .toList(growable: false);
  }
}
