import 'package:cloud_firestore/cloud_firestore.dart';

const _onboardingFields = <String>{
  'nickname',
  'gender',
  'region',
  'education',
  'height',
  'age',
  'grade',
  'isRa',
  'mbti',
  'loveLanguages',
  'relationship',
  'lifestyle',
  'major',
  'department',
  'selfIntroduction',
  'interests',
  'keywords',
  'photoUrls',
  'profileQa',
  'campusLifeZones',
  'campusLifeZoneLabels',
};

const _idealTypeFields = <String>{
  'minAge',
  'maxAge',
  'minHeight',
  'maxHeight',
  'preferredMbti',
  'preferredDepartments',
  'preferredPersonalities',
  'preferredLifestyles',
  'skipped',
};

const _privacyFields = <String>{'avoidSameDepartment'};

const _lifestyleFields = <String>{
  'drinking',
  'smoking',
  'exercise',
  'religion',
};

/// Builds Firestore field-path updates for one onboarding step.
///
/// Every writable field is allowlisted. Firestore interprets dots and bracket
/// characters in a map key as field-path syntax, so arbitrary client-provided
/// keys must never become update paths.
Map<String, dynamic> buildOnboardingFieldUpdates(Map<String, dynamic> fields) {
  return _buildScopedFieldUpdates(
    root: 'onboarding',
    fields: fields,
    updatedAtField: 'onboardingUpdatedAt',
    allowedFields: _onboardingFields,
    nestedFields: const {'lifestyle': _lifestyleFields},
  );
}

Map<String, dynamic> buildOnboardingFieldUpdate({
  required String fieldName,
  required dynamic value,
}) {
  return buildOnboardingFieldUpdates({fieldName: value});
}

Map<String, dynamic> buildIdealTypeFieldUpdates(Map<String, dynamic> fields) {
  return _buildScopedFieldUpdates(
    root: 'idealType',
    fields: fields,
    updatedAtField: 'idealTypeUpdatedAt',
    allowedFields: _idealTypeFields,
    nestedFields: const {'preferredLifestyles': _lifestyleFields},
  );
}

Map<String, dynamic> buildIdealTypeFieldUpdate({
  required String fieldName,
  required dynamic value,
}) {
  return buildIdealTypeFieldUpdates({fieldName: value});
}

Map<String, dynamic> buildPrivacyFieldUpdates(Map<String, dynamic> fields) {
  return _buildScopedFieldUpdates(
    root: 'privacySettings',
    fields: fields,
    updatedAtField: 'privacySettingsUpdatedAt',
    allowedFields: _privacyFields,
    nestedFields: const {},
  );
}

Map<String, dynamic> _buildScopedFieldUpdates({
  required String root,
  required Map<String, dynamic> fields,
  required String updatedAtField,
  required Set<String> allowedFields,
  required Map<String, Set<String>> nestedFields,
}) {
  final updates = <String, dynamic>{
    updatedAtField: FieldValue.serverTimestamp(),
  };
  for (final entry in fields.entries) {
    final fieldName = entry.key;
    _validateFieldName(fieldName, allowedFields: allowedFields, root: root);
    _appendFieldUpdates(
      updates,
      path: '$root.$fieldName',
      value: entry.value,
      allowedChildren: nestedFields[fieldName],
    );
  }
  return updates;
}

void _appendFieldUpdates(
  Map<String, dynamic> updates, {
  required String path,
  required dynamic value,
  Set<String>? allowedChildren,
}) {
  if (value is Map) {
    if (allowedChildren == null) {
      throw ArgumentError('Map value is not allowed at field path "$path".');
    }
    // An empty map must not replace the whole nested object. Callers can
    // clear a specific child by sending that child as null or delete.
    for (final entry in value.entries) {
      final childName = entry.key;
      if (childName is! String ||
          !allowedChildren.contains(childName) ||
          !_isSafeFieldSegment(childName)) {
        throw ArgumentError(
          'Unsupported nested field path "$path.$childName".',
        );
      }
      _appendFieldUpdates(
        updates,
        path: '$path.$childName',
        value: entry.value,
      );
    }
    return;
  }

  if (allowedChildren != null && (value == null || value is FieldValue)) {
    throw ArgumentError(
      'Nested field "$path" must be updated through an allowlisted child.',
    );
  }

  if (updates.containsKey(path)) {
    throw ArgumentError('Duplicate Firestore field path "$path".');
  }
  updates[path] = value;
}

void _validateFieldName(
  String fieldName, {
  required Set<String> allowedFields,
  required String root,
}) {
  if (!allowedFields.contains(fieldName) || !_isSafeFieldSegment(fieldName)) {
    throw ArgumentError('Unsupported Firestore field path "$root.$fieldName".');
  }
}

bool _isSafeFieldSegment(String value) {
  return RegExp(r'^[A-Za-z][A-Za-z0-9]*$').hasMatch(value);
}
