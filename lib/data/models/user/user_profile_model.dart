/// 사용자 프로필 모델 (상세 정보)
class UserProfileModel {
  final String userId;
  final List<String> photoUrls;
  final List<String> keywords;
  final List<ProfileQuestion> profileQuestions;
  final IdealTypePreferences? idealType;

  const UserProfileModel({
    required this.userId,
    this.photoUrls = const [],
    this.keywords = const [],
    this.profileQuestions = const [],
    this.idealType,
  });

  factory UserProfileModel.fromJson(Map<String, dynamic> json) {
    return UserProfileModel(
      userId: json['userId'] as String,
      photoUrls:
          (json['photoUrls'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      keywords:
          (json['keywords'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      profileQuestions:
          (json['profileQuestions'] as List<dynamic>?)
              ?.map((e) => ProfileQuestion.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      idealType: json['idealType'] != null
          ? IdealTypePreferences.fromJson(
              json['idealType'] as Map<String, dynamic>,
            )
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'userId': userId,
      'photoUrls': photoUrls,
      'keywords': keywords,
      'profileQuestions': profileQuestions.map((e) => e.toJson()).toList(),
      'idealType': idealType?.toJson(),
    };
  }
}

/// 프로필 문답
class ProfileQuestion {
  final String question;
  final String answer;

  const ProfileQuestion({required this.question, required this.answer});

  factory ProfileQuestion.fromJson(Map<String, dynamic> json) {
    return ProfileQuestion(
      question: json['question'] as String,
      answer: json['answer'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {'question': question, 'answer': answer};
  }
}

/// 이상형 설정
class IdealTypePreferences {
  final int? minAge;
  final int? maxAge;
  final int? minHeight;
  final int? maxHeight;
  final List<String> preferredMbti;
  final List<String> preferredDepartments;
  final List<String> preferredPersonalities;
  final List<String> preferredLifestyles;

  const IdealTypePreferences({
    this.minAge,
    this.maxAge,
    this.minHeight,
    this.maxHeight,
    this.preferredMbti = const [],
    this.preferredDepartments = const [],
    this.preferredPersonalities = const [],
    this.preferredLifestyles = const [],
  });

  factory IdealTypePreferences.fromJson(Map<String, dynamic> json) {
    return IdealTypePreferences(
      minAge: json['minAge'] as int?,
      maxAge: json['maxAge'] as int?,
      minHeight: json['minHeight'] as int?,
      maxHeight: json['maxHeight'] as int?,
      preferredMbti:
          (json['preferredMbti'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      preferredDepartments:
          (json['preferredDepartments'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      preferredPersonalities:
          (json['preferredPersonalities'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      preferredLifestyles:
          (json['preferredLifestyles'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'minAge': minAge,
      'maxAge': maxAge,
      'minHeight': minHeight,
      'maxHeight': maxHeight,
      'preferredMbti': preferredMbti,
      'preferredDepartments': preferredDepartments,
      'preferredPersonalities': preferredPersonalities,
      'preferredLifestyles': preferredLifestyles,
    };
  }
}
