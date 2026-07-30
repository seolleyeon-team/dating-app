import 'package:cloud_firestore/cloud_firestore.dart';

import 'festival_recommendation_models.dart';
import 'festival_vector_math.dart';

/// AI 프로필 카드 스와이프 → 호감도 맵 + preference vector.
class FestivalTasteAffinityBuilder {
  FestivalTasteAffinityBuilder(this._db);

  final FirebaseFirestore _db;

  static const double likeWeight = 1.0;
  static const double dislikeWeight = 0.65;

  Future<({
    Map<String, double> affinities,
    FestivalPreferenceVector? preferenceVector,
  })> buildForTicket(String ticketId) async {
    final swipesSnap = await _db
        .collection('festivalTickets')
        .doc(ticketId)
        .collection('tasteSwipes')
        .get();

    final affinityScores = <String, double>{};
    final positiveSamples = <({List<double> vector, double weight})>[];
    final negativeSamples = <({List<double> vector, double weight})>[];

    for (final doc in swipesSnap.docs) {
      final data = doc.data();
      final code = (data['aiProfileCode'] as String?)?.trim() ?? '';
      if (code.isEmpty) continue;

      final liked = data['liked'] == true;
      affinityScores[code] = liked ? 1.0 : 0.0;

      final embedding = await _loadAiEmbedding(code);
      if (embedding == null) continue;

      if (liked) {
        positiveSamples.add((vector: embedding, weight: likeWeight));
      } else {
        negativeSamples.add((vector: embedding, weight: dislikeWeight));
      }
    }

    final posMean = FestivalVectorMath.weightedMean(positiveSamples);
    final negMean = FestivalVectorMath.weightedMean(negativeSamples);

    List<double>? preference;
    var confidence = 0.0;

    if (posMean != null && negMean != null) {
      preference = FestivalVectorMath.l2Normalize(
        List<double>.generate(
          posMean.length,
          (index) => posMean[index] - (dislikeWeight * negMean[index]),
        ),
      );
      confidence = _clipConfidence(positiveSamples.length, negativeSamples.length);
    } else if (posMean != null) {
      preference = posMean;
      confidence = _clipConfidence(positiveSamples.length, 0);
    }

    final preferenceVector = preference == null
        ? null
        : FestivalPreferenceVector(
            vector: preference,
            dims: preference.length,
            modelId: 'festival-clip-v1',
            confidence: confidence,
          );

    return (affinities: affinityScores, preferenceVector: preferenceVector);
  }

  Future<void> persistForTicket(
    String ticketId, {
    required Map<String, double> affinities,
    FestivalPreferenceVector? preferenceVector,
  }) async {
    final payload = <String, Object?>{
      'aiProfileAffinities': affinities,
      'aiProfileAffinityUpdatedAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    };

    if (preferenceVector != null && preferenceVector.isValid) {
      payload['preferenceVector'] = preferenceVector.toMap();
    }

    await _db.collection('festivalTickets').doc(ticketId).set(
      payload,
      SetOptions(merge: true),
    );
  }

  Future<List<double>?> _loadAiEmbedding(String code) async {
    final snap = await _db.collection('festivalAiEmbeddings').doc(code).get();
    if (!snap.exists) return null;
    final data = snap.data();
    final raw = data?['vector'];
    if (raw is! List || raw.isEmpty) return null;
    return raw.map((value) => (value as num).toDouble()).toList(growable: false);
  }

  double _clipConfidence(int positiveCount, int negativeCount) {
    final pairScore = (positiveCount / 6).clamp(0.0, 1.0);
    final strongScore = (positiveCount / 3).clamp(0.0, 1.0);
    final negPenalty = negativeCount > 0 ? 0.08 : 0.0;
    return (0.15 + 0.45 * pairScore + 0.4 * strongScore - negPenalty).clamp(
      0.0,
      1.0,
    );
  }
}
