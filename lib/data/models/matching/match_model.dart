/// 매칭 카드 모델
class MatchModel {
  final String id;
  final MatchedUser user;
  final List<String> photoUrls;
  final double matchScore;
  final List<String> commonInterests;
  final DateTime createdAt;

  const MatchModel({
    required this.id,
    required this.user,
    this.photoUrls = const [],
    required this.matchScore,
    this.commonInterests = const [],
    required this.createdAt,
  });

  factory MatchModel.fromJson(Map<String, dynamic> json) {
    return MatchModel(
      id: json['id'] as String,
      user: MatchedUser.fromJson(json['user'] as Map<String, dynamic>),
      photoUrls:
          (json['photoUrls'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      matchScore: (json['matchScore'] as num).toDouble(),
      commonInterests:
          (json['commonInterests'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      createdAt: DateTime.parse(json['createdAt'] as String),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'user': user.toJson(),
      'photoUrls': photoUrls,
      'matchScore': matchScore,
      'commonInterests': commonInterests,
      'createdAt': createdAt.toIso8601String(),
    };
  }
}

/// 매칭 상대 사용자 정보
class MatchedUser {
  final String id;
  final String nickname;
  final int age;
  final String? department;
  final String? profileImageUrl;

  const MatchedUser({
    required this.id,
    required this.nickname,
    required this.age,
    this.department,
    this.profileImageUrl,
  });

  factory MatchedUser.fromJson(Map<String, dynamic> json) {
    return MatchedUser(
      id: json['id'] as String,
      nickname: json['nickname'] as String,
      age: json['age'] as int,
      department: json['department'] as String?,
      profileImageUrl: json['profileImageUrl'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'nickname': nickname,
      'age': age,
      'department': department,
      'profileImageUrl': profileImageUrl,
    };
  }
}
