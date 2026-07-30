import 'dart:math' as math;

class FestivalVectorMath {
  static List<double> l2Normalize(List<double> vector) {
    var sum = 0.0;
    for (final value in vector) {
      sum += value * value;
    }
    if (sum <= 1e-12) return List<double>.from(vector);
    final norm = math.sqrt(sum);
    return vector.map((value) => value / norm).toList(growable: false);
  }

  static double cosineSimilarity(List<double> a, List<double> b) {
    if (a.isEmpty || b.isEmpty || a.length != b.length) return 0;
    var dot = 0.0;
    var normA = 0.0;
    var normB = 0.0;
    for (var i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }
    if (normA <= 1e-12 || normB <= 1e-12) return 0;
    return dot / (math.sqrt(normA) * math.sqrt(normB));
  }

  static List<double>? weightedMean(
    List<({List<double> vector, double weight})> samples,
  ) {
    if (samples.isEmpty) return null;
    final dims = samples.first.vector.length;
    final acc = List<double>.filled(dims, 0);
    var weightSum = 0.0;

    for (final sample in samples) {
      if (sample.vector.length != dims || sample.weight <= 0) continue;
      weightSum += sample.weight;
      for (var i = 0; i < dims; i++) {
        acc[i] += sample.vector[i] * sample.weight;
      }
    }

    if (weightSum <= 1e-12) return null;
    return l2Normalize(acc.map((value) => value / weightSum).toList());
  }
}
