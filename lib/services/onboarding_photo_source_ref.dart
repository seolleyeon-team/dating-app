class OnboardingPhotoSourceRef {
  const OnboardingPhotoSourceRef({
    required this.photoId,
    required this.slotIndex,
    required this.objectGeneration,
  });

  final String photoId;
  final int slotIndex;
  final String objectGeneration;

  bool get isValid =>
      RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$').hasMatch(photoId) &&
      slotIndex >= 0 &&
      slotIndex <= 5 &&
      RegExp(r'^[1-9][0-9]*$').hasMatch(objectGeneration);

  Map<String, dynamic> toMap() => <String, dynamic>{
    'photoId': photoId,
    'slotIndex': slotIndex,
    'objectGeneration': objectGeneration,
  };

  static OnboardingPhotoSourceRef? tryParse(Map<String, dynamic> data) {
    final candidate = OnboardingPhotoSourceRef(
      photoId: data['photoId']?.toString().trim() ?? '',
      slotIndex: int.tryParse(data['slotIndex']?.toString() ?? '') ?? -1,
      objectGeneration: data['objectGeneration']?.toString().trim() ?? '',
    );
    return candidate.isValid ? candidate : null;
  }
}
