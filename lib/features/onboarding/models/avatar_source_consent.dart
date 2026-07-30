import 'package:flutter/foundation.dart';

@immutable
class AvatarSourceConsent {
  const AvatarSourceConsent({
    this.avatarGeneration = true,
    this.clipRecommendation = false,
    this.sourcePhotoRetention = false,
  });

  final bool avatarGeneration;
  final bool clipRecommendation;
  final bool sourcePhotoRetention;

  Map<String, bool> toPayloadMap() {
    return <String, bool>{
      'avatarGeneration': avatarGeneration,
      'clipRecommendation': clipRecommendation,
      'sourcePhotoRetention': sourcePhotoRetention,
    };
  }

  AvatarSourceConsent copyWith({
    bool? clipRecommendation,
    bool? sourcePhotoRetention,
  }) {
    return AvatarSourceConsent(
      avatarGeneration: avatarGeneration,
      clipRecommendation: clipRecommendation ?? this.clipRecommendation,
      sourcePhotoRetention: sourcePhotoRetention ?? this.sourcePhotoRetention,
    );
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        other is AvatarSourceConsent &&
            other.avatarGeneration == avatarGeneration &&
            other.clipRecommendation == clipRecommendation &&
            other.sourcePhotoRetention == sourcePhotoRetention;
  }

  @override
  int get hashCode =>
      Object.hash(avatarGeneration, clipRecommendation, sourcePhotoRetention);
}
