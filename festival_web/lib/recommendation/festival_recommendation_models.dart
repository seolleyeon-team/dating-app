class FestivalPreferenceVector {
  final List<double> vector;
  final int dims;
  final String modelId;
  final double confidence;

  const FestivalPreferenceVector({
    required this.vector,
    required this.dims,
    required this.modelId,
    required this.confidence,
  });

  factory FestivalPreferenceVector.fromMap(Map<String, dynamic>? data) {
    if (data == null) {
      return const FestivalPreferenceVector(
        vector: [],
        dims: 0,
        modelId: '',
        confidence: 0,
      );
    }

    final rawVector = data['vector'];
    final vector = rawVector is List
        ? rawVector
              .map((value) => (value as num?)?.toDouble() ?? 0)
              .toList(growable: false)
        : <double>[];

    return FestivalPreferenceVector(
      vector: vector,
      dims: data['dims'] is int ? data['dims'] as int : vector.length,
      modelId: data['modelId'] as String? ?? 'festival-clip-v1',
      confidence: (data['confidence'] as num?)?.toDouble() ?? 0,
    );
  }

  Map<String, Object?> toMap() {
    return {
      'vector': vector,
      'dims': dims,
      'modelId': modelId,
      'confidence': confidence,
      'computedAt': DateTime.now().toUtc().toIso8601String(),
      'source': 'festival_taste_swipes',
    };
  }

  bool get isValid => vector.isNotEmpty;
}

class FestivalRankedCandidate {
  final String ticketId;
  final double score;
  final int rank;
  final String source;

  const FestivalRankedCandidate({
    required this.ticketId,
    required this.score,
    required this.rank,
    required this.source,
  });
}
