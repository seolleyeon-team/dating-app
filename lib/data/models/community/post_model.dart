import 'package:cloud_firestore/cloud_firestore.dart';

class PostModel {
  final String postId;

  /// 대나무숲은 익명 게시판이다 (P0-3). public 문서에는 작성자 정보가 없고,
  /// 이 모델도 작성자를 담지 않는다. "내 글인가" 는 비공개 소유권 매핑으로만
  /// 판단한다 (`FirestoreCommunityRepository.fetchMyPostIds`).
  final String content;

  /// 상단 탭용 카테고리
  /// 예: 전체, 인기, 설렘, 고민, 일상, 질문
  final String category;

  /// 예: 짝사랑, 첫만남, 썸, 재회 ...
  final List<String> tags;

  final DateTime? createdAt;
  final DateTime? updatedAt;

  final int likeCount;
  final int commentCount;

  /// 최근 7일 인기 점수
  /// 인기 탭 정렬용
  final int score7d;

  final bool isDeleted;

  const PostModel({
    required this.postId,
    required this.content,
    required this.category,
    required this.tags,
    required this.createdAt,
    required this.updatedAt,
    required this.likeCount,
    required this.commentCount,
    required this.score7d,
    required this.isDeleted,
  });

  factory PostModel.empty() {
    return const PostModel(
      postId: '',
      content: '',
      category: '전체',
      tags: [],
      createdAt: null,
      updatedAt: null,
      likeCount: 0,
      commentCount: 0,
      score7d: 0,
      isDeleted: false,
    );
  }

  PostModel copyWith({
    String? postId,
    String? content,
    String? category,
    List<String>? tags,
    DateTime? createdAt,
    DateTime? updatedAt,
    int? likeCount,
    int? commentCount,
    int? score7d,
    bool? isDeleted,
  }) {
    return PostModel(
      postId: postId ?? this.postId,
      content: content ?? this.content,
      category: category ?? this.category,
      tags: tags ?? this.tags,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      likeCount: likeCount ?? this.likeCount,
      commentCount: commentCount ?? this.commentCount,
      score7d: score7d ?? this.score7d,
      isDeleted: isDeleted ?? this.isDeleted,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'postId': postId,
      'content': content,
      'category': category,
      'tags': tags,
      'createdAt': createdAt != null ? Timestamp.fromDate(createdAt!) : null,
      'updatedAt': updatedAt != null ? Timestamp.fromDate(updatedAt!) : null,
      'likeCount': likeCount,
      'commentCount': commentCount,
      'score7d': score7d,
      'isDeleted': isDeleted,
    };
  }

  factory PostModel.fromMap(Map<String, dynamic> map, {String? documentId}) {
    return PostModel(
      postId: (map['postId'] ?? documentId ?? '').toString(),
      content: (map['content'] ?? '').toString(),
      category: (map['category'] ?? '전체').toString(),
      tags: _parseTags(map['tags']),
      createdAt: _parseDateTime(map['createdAt']),
      updatedAt: _parseDateTime(map['updatedAt']),
      likeCount: _parseInt(map['likeCount']),
      commentCount: _parseInt(map['commentCount']),
      score7d: _parseInt(map['score7d']),
      isDeleted: map['isDeleted'] == true,
    );
  }

  factory PostModel.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? <String, dynamic>{};
    return PostModel.fromMap(data, documentId: doc.id);
  }

  static List<String> _parseTags(dynamic raw) {
    if (raw is List) {
      return raw.map((e) => e.toString()).where((e) => e.isNotEmpty).toList();
    }
    return [];
  }

  static int _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return 0;
  }

  static DateTime? _parseDateTime(dynamic value) {
    if (value == null) return null;
    if (value is Timestamp) return value.toDate();
    if (value is DateTime) return value;
    return null;
  }

  /// 기존 community UI에서 제목처럼 쓸 수 있게 짧은 미리보기 제공
  String get previewText {
    final normalized = content.replaceAll('\n', ' ').trim();
    if (normalized.length <= 60) return normalized;
    return '${normalized.substring(0, 60)}...';
  }

  /// 기존 리스트 화면에서 상대시간 표시할 때 쓰기 좋음
  String get relativeTimeLabel {
    if (createdAt == null) return '';

    final now = DateTime.now();
    final diff = now.difference(createdAt!);

    if (diff.inSeconds < 60) return '방금 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';
    return '${createdAt!.month}/${createdAt!.day}';
  }
}
