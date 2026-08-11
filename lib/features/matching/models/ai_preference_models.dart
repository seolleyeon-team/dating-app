enum AiPreferenceShotType { faceCard, vibeCard, silhouetteCard }

const List<AiPreferenceShotType> aiPreferenceShotTypes = <AiPreferenceShotType>[
  AiPreferenceShotType.faceCard,
  AiPreferenceShotType.vibeCard,
  AiPreferenceShotType.silhouetteCard,
];

String aiPreferenceShotFileName(AiPreferenceShotType shotType) {
  return switch (shotType) {
    AiPreferenceShotType.faceCard => 'face_card.png',
    AiPreferenceShotType.vibeCard => 'vibe_card.png',
    AiPreferenceShotType.silhouetteCard => 'silhouette_card.png',
  };
}

String aiPreferenceShotTypeName(AiPreferenceShotType shotType) {
  return switch (shotType) {
    AiPreferenceShotType.faceCard => 'face_card',
    AiPreferenceShotType.vibeCard => 'vibe_card',
    AiPreferenceShotType.silhouetteCard => 'silhouette_card',
  };
}

String buildAiProfileStoragePath({
  required String gender,
  required String profileId,
  required AiPreferenceShotType shotType,
}) {
  _validateGender(gender);
  _validateProfileId(profileId);
  return 'ai_profiles/$gender/$profileId/${aiPreferenceShotFileName(shotType)}';
}

class AiPreferenceImage {
  const AiPreferenceImage({
    required this.identityId,
    required this.gender,
    required this.profileId,
    required this.shotType,
    required this.storagePath,
    this.downloadUrl,
  });

  final String identityId;
  final String gender;
  final String profileId;
  final AiPreferenceShotType shotType;
  final String storagePath;
  final String? downloadUrl;

  AiPreferenceImage withDownloadUrl(String? url) {
    return AiPreferenceImage(
      identityId: identityId,
      gender: gender,
      profileId: profileId,
      shotType: shotType,
      storagePath: storagePath,
      downloadUrl: url,
    );
  }
}

class AiPreferenceIdentity {
  AiPreferenceIdentity._({
    required this.identityId,
    required this.gender,
    required this.profileId,
    required Iterable<AiPreferenceImage> images,
  }) : images = List<AiPreferenceImage>.unmodifiable(images);

  factory AiPreferenceIdentity.create({
    required String gender,
    required String profileId,
  }) {
    _validateGender(gender);
    _validateProfileId(profileId);

    final identityId = '${gender}_$profileId';
    return AiPreferenceIdentity._(
      identityId: identityId,
      gender: gender,
      profileId: profileId,
      images: aiPreferenceShotTypes.map(
        (shotType) => AiPreferenceImage(
          identityId: identityId,
          gender: gender,
          profileId: profileId,
          shotType: shotType,
          storagePath: buildAiProfileStoragePath(
            gender: gender,
            profileId: profileId,
            shotType: shotType,
          ),
        ),
      ),
    );
  }

  factory AiPreferenceIdentity.fromIdentityId(String identityId) {
    final match = RegExp(r'^(male|female)_(\d+)$').firstMatch(identityId);
    if (match == null) {
      throw FormatException('Invalid AI preference identity ID: $identityId');
    }

    return AiPreferenceIdentity.create(
      gender: match.group(1)!,
      profileId: match.group(2)!,
    );
  }

  final String identityId;
  final String gender;
  final String profileId;
  final List<AiPreferenceImage> images;

  AiPreferenceIdentity withImages(Iterable<AiPreferenceImage> resolvedImages) {
    return AiPreferenceIdentity._(
      identityId: identityId,
      gender: gender,
      profileId: profileId,
      images: resolvedImages,
    );
  }

  AiPreferenceIdentity orderedBy(Iterable<AiPreferenceShotType> order) {
    final requestedOrder = List<AiPreferenceShotType>.of(order);
    if (requestedOrder.length != aiPreferenceShotTypes.length ||
        requestedOrder.toSet().length != aiPreferenceShotTypes.length ||
        !requestedOrder.every(aiPreferenceShotTypes.contains)) {
      throw ArgumentError.value(
        order,
        'order',
        'must contain each AI preference shot type exactly once',
      );
    }

    final imagesByShot = <AiPreferenceShotType, AiPreferenceImage>{
      for (final image in images) image.shotType: image,
    };
    return withImages(
      requestedOrder.map((shotType) => imagesByShot[shotType]!),
    );
  }
}

void _validateGender(String gender) {
  if (gender != 'male' && gender != 'female') {
    throw ArgumentError.value(gender, 'gender', 'must be male or female');
  }
}

void _validateProfileId(String profileId) {
  if (!RegExp(r'^\d+$').hasMatch(profileId)) {
    throw ArgumentError.value(
      profileId,
      'profileId',
      'must be a non-empty string of digits',
    );
  }
}
