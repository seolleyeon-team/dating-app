import '../constants/legal_texts.dart';

/// The user's terms acceptance as collected on the terms screen, before any
/// account exists (terms-gate contract §2/§4).
///
/// This is the PRE-AUTH carrier only. It is never the authority for any gate:
/// the server-owned `users/{appUserId}.termsAcceptance` map is (contract §3).
/// Nothing in this class may be fabricated — `ageOver18` is not a UI item and
/// must not appear in any record (contract §2, finding F2).
class PendingTermsAcceptance {
  const PendingTermsAcceptance({
    required this.version,
    required this.acceptedDocumentIds,
    required this.optionalConsents,
  });

  /// Authority is `lib/constants/legal_texts.dart` (contract §2). All four
  /// must be accepted before the gate opens.
  static const List<String> requiredDocumentIds = <String>[
    'termsOfService',
    'privacyPolicy',
    'kakaoNamePhone',
    'ageOver20',
  ];

  /// Never blocking (contract §2). Progression must remain possible with
  /// every one of these off.
  static const List<String> optionalConsentKeys = <String>[
    'marketing',
    'push',
    'email',
  ];

  final String version;
  final List<String> acceptedDocumentIds;
  final Map<String, bool> optionalConsents;

  bool get coversRequiredDocuments =>
      requiredDocumentIds.every(acceptedDocumentIds.contains);

  bool accepted(String documentId) => acceptedDocumentIds.contains(documentId);

  bool optional(String key) => optionalConsents[key] == true;

  /// Normalized optional map: every key present, every value a real bool.
  Map<String, bool> get normalizedOptionalConsents => <String, bool>{
    for (final key in optionalConsentKeys) key: optional(key),
  };

  /// Callable payload for `sendPrimaryStudentEmailLink` (§4) and
  /// `recordTermsAcceptance` (§6). Carries no identity and no free text.
  Map<String, dynamic> toCallablePayload() => <String, dynamic>{
    'version': version,
    'acceptedDocumentIds': List<String>.from(acceptedDocumentIds),
    'optionalConsents': normalizedOptionalConsents,
  };

  Map<String, dynamic> toStorageMap({String? agreedAtClientIso}) =>
      <String, dynamic>{
        'version': version,
        'acceptedDocumentIds': List<String>.from(acceptedDocumentIds),
        'optionalConsents': normalizedOptionalConsents,
        'agreedAtClientIso':
            agreedAtClientIso ?? DateTime.now().toUtc().toIso8601String(),
      };

  /// Fail closed: any malformed or partial blob yields `null` so the caller
  /// treats it as "no acceptance recorded" rather than silently proceeding.
  static PendingTermsAcceptance? fromStorageMap(Map<String, dynamic>? raw) {
    if (raw == null) return null;

    final version = raw['version']?.toString().trim() ?? '';
    if (version.isEmpty) return null;

    final rawIds = raw['acceptedDocumentIds'];
    if (rawIds is! List) return null;
    final ids = rawIds
        .map((id) => id?.toString().trim() ?? '')
        .where((id) => id.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (ids.isEmpty) return null;

    final rawOptional = raw['optionalConsents'];
    final optional = <String, bool>{
      for (final key in optionalConsentKeys)
        key: rawOptional is Map && rawOptional[key] == true,
    };

    return PendingTermsAcceptance(
      version: version,
      acceptedDocumentIds: ids,
      optionalConsents: optional,
    );
  }

  /// Builds the acceptance for the CURRENT repo-wide document version.
  factory PendingTermsAcceptance.current({
    required List<String> acceptedDocumentIds,
    required Map<String, bool> optionalConsents,
  }) => PendingTermsAcceptance(
    version: LegalTexts.version,
    acceptedDocumentIds: acceptedDocumentIds,
    optionalConsents: optionalConsents,
  );
}
