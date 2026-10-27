import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../../../data/models/community/post_model.dart';
import '../../../data/repositories/community_repository.dart';
import '../../../data/repositories/firestore_community_repository.dart';

/// 대나무숲 목록 상태.
///
/// P0-3: 게시글 모델에는 작성자가 없다. "내 글" 표시는 페이지마다 비공개
/// 소유권 매핑을 한 번 조회해 얻은 [isMine] 집합으로만 한다. 앱 전역
/// provider 라서 로그인 계정이 바뀌면 이전 계정의 목록·"내 글" 표시·커서를
/// 모두 버린다 — 남기면 다음 계정에게 이전 계정이 쓴 글이 "내 글" 로 보인다.
class CommunityProvider extends ChangeNotifier {
  CommunityProvider({
    CommunityRepository? repository,
    String Function()? currentUid,
  }) : _repository = repository ?? FirestoreCommunityRepository(),
       _currentUid =
           currentUid ??
           (() => FirebaseAuth.instance.currentUser?.uid.trim() ?? '');

  final CommunityRepository _repository;
  final String Function() _currentUid;

  /// 지금 캐시된 상태가 속한 계정. 다르면 [_resetIfAccountChanged] 가 비운다.
  String? _sessionUid;
  String _selectedTab = '전체';
  bool _isInitialized = false;

  static const String myPostsTab = FirestoreCommunityRepository.myPostsTab;

  static const List<String> tabs = [
    '전체',
    '인기',
    '설렘',
    '고민',
    '일상',
    '질문',
    myPostsTab,
  ];

  final Map<String, List<PostModel>> _postsByTab = {
    for (final tab in tabs) tab: <PostModel>[],
  };

  final Map<String, Object?> _cursorByTab = {for (final tab in tabs) tab: null};

  final Map<String, bool> _isLoadingByTab = {
    for (final tab in tabs) tab: false,
  };

  final Map<String, bool> _isLoadingMoreByTab = {
    for (final tab in tabs) tab: false,
  };

  final Map<String, bool> _hasMoreByTab = {for (final tab in tabs) tab: true};

  /// 화면에 나온 글 중 내가 쓴 글 (비공개 매핑 조회 결과).
  final Set<String> _myPostIds = <String>{};

  String get selectedTab => _selectedTab;
  bool get isInitialized => _isInitialized;

  List<PostModel> get posts => _postsByTab[_selectedTab] ?? const [];
  bool get isLoading => _isLoadingByTab[_selectedTab] ?? false;
  bool get isLoadingMore => _isLoadingMoreByTab[_selectedTab] ?? false;
  bool get hasMore => _hasMoreByTab[_selectedTab] ?? false;

  List<PostModel> postsOf(String tab) => _postsByTab[tab] ?? const [];
  bool isLoadingOf(String tab) => _isLoadingByTab[tab] ?? false;
  bool isLoadingMoreOf(String tab) => _isLoadingMoreByTab[tab] ?? false;
  bool hasMoreOf(String tab) => _hasMoreByTab[tab] ?? false;

  /// 이 글을 로그인한 사용자가 썼는가 (삭제 버튼 vs 신고 버튼).
  bool isMine(String postId) => _myPostIds.contains(postId);

  /// 계정이 바뀌었으면 이전 계정의 모든 캐시를 버린다. 바뀌었으면 true.
  bool _resetIfAccountChanged() {
    final uid = _currentUid();
    if (_sessionUid == uid) return false;
    _sessionUid = uid;
    for (final tab in tabs) {
      _postsByTab[tab] = <PostModel>[];
      _cursorByTab[tab] = null;
      _hasMoreByTab[tab] = true;
      _isLoadingByTab[tab] = false;
      _isLoadingMoreByTab[tab] = false;
    }
    _myPostIds.clear();
    return true;
  }

  Future<void> initialize() async {
    final accountChanged = _resetIfAccountChanged();
    if (_isInitialized && !accountChanged) return;
    _isInitialized = true;

    debugPrint(
      'CommunityProvider initialize ${PrivacyLogUtils.idFingerprint(_sessionUid)}',
    );

    await loadPosts(tab: _selectedTab, forceRefresh: true);
  }

  Future<void> changeTab(String tab) async {
    if (!tabs.contains(tab)) return;
    _resetIfAccountChanged();

    _selectedTab = tab;
    notifyListeners();

    final hasLoaded = (_postsByTab[tab] ?? []).isNotEmpty;
    if (!hasLoaded) {
      await loadPosts(tab: tab, forceRefresh: true);
    }
  }

  Future<void> _rememberOwnership(String tab, List<PostModel> page) async {
    if (page.isEmpty) return;
    if (tab == myPostsTab) {
      _myPostIds.addAll(page.map((p) => p.postId));
      return;
    }
    try {
      _myPostIds.addAll(
        await _repository.fetchMyPostIds(page.map((p) => p.postId)),
      );
    } catch (e) {
      // 조회 실패 시 "내 글" 표시만 빠진다 (삭제 대신 신고 버튼). 권한 경계는
      // 서버 callable 이 다시 확인한다.
      debugPrint(
        'CommunityProvider ownership lookup error: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  Future<void> loadPosts({
    required String tab,
    bool forceRefresh = false,
  }) async {
    if (!tabs.contains(tab)) return;
    _resetIfAccountChanged();
    if ((_isLoadingByTab[tab] ?? false) && !forceRefresh) return;

    final uidAtStart = _sessionUid;
    _isLoadingByTab[tab] = true;

    if (forceRefresh) {
      _postsByTab[tab] = [];
      _cursorByTab[tab] = null;
      _hasMoreByTab[tab] = true;
    }

    notifyListeners();

    try {
      final page = await _repository.fetchPostsPage(tab: tab, limit: 5);
      // 응답을 기다리는 사이 계정이 바뀌었으면 결과를 버린다.
      if (_currentUid() != uidAtStart) return;
      await _rememberOwnership(tab, page.posts);

      _postsByTab[tab] = page.posts;
      _cursorByTab[tab] = page.cursor;
      _hasMoreByTab[tab] = page.hasMore;
    } catch (e) {
      debugPrint(
        'CommunityProvider loadPosts error: ${PrivacyLogUtils.errorSummary(e)}',
      );
    } finally {
      _isLoadingByTab[tab] = false;
      notifyListeners();
    }
  }

  Future<void> loadMore({String? tab}) async {
    final targetTab = tab ?? _selectedTab;
    if (!tabs.contains(targetTab)) return;
    if (_resetIfAccountChanged()) {
      notifyListeners();
      return;
    }

    if (_isLoadingMoreByTab[targetTab] == true) return;
    if (_hasMoreByTab[targetTab] != true) return;

    final cursor = _cursorByTab[targetTab];
    if (cursor == null) return;

    final uidAtStart = _sessionUid;
    _isLoadingMoreByTab[targetTab] = true;
    notifyListeners();

    try {
      final page = await _repository.fetchPostsPage(
        tab: targetTab,
        limit: 5,
        cursor: cursor,
      );
      if (_currentUid() != uidAtStart) return;
      await _rememberOwnership(targetTab, page.posts);

      final seen = {for (final p in _postsByTab[targetTab] ?? []) p.postId};
      _postsByTab[targetTab] = [
        ...(_postsByTab[targetTab] ?? <PostModel>[]),
        ...page.posts.where((p) => !seen.contains(p.postId)),
      ];
      _cursorByTab[targetTab] = page.cursor;
      _hasMoreByTab[targetTab] = page.hasMore;
    } catch (e) {
      debugPrint(
        'CommunityProvider loadMore error: ${PrivacyLogUtils.errorSummary(e)}',
      );
    } finally {
      _isLoadingMoreByTab[targetTab] = false;
      notifyListeners();
    }
  }

  Future<String> createPost({
    required String content,
    required String category,
    required List<String> tags,
  }) async {
    try {
      final postId = await _repository.createPost(
        content: content,
        category: category,
        tags: tags,
      );
      _myPostIds.add(postId);

      await refreshAfterPostCreated(category: category);
      return postId;
    } catch (e) {
      debugPrint(
        'CommunityProvider createPost error: ${PrivacyLogUtils.errorSummary(e)}',
      );
      rethrow;
    }
  }

  Future<void> refreshAfterPostCreated({required String category}) async {
    await loadPosts(tab: '전체', forceRefresh: true);

    if (tabs.contains(category)) {
      await loadPosts(tab: category, forceRefresh: true);
    }

    await loadPosts(tab: '인기', forceRefresh: true);
    await loadPosts(tab: myPostsTab, forceRefresh: true);
  }

  Future<void> refreshCurrentTab() async {
    await loadPosts(tab: _selectedTab, forceRefresh: true);
  }

  void _sortPostsForTab(String tab) {
    final current = [...(_postsByTab[tab] ?? const <PostModel>[])];

    if (tab == '인기') {
      current.sort((a, b) {
        final scoreCompare = b.score7d.compareTo(a.score7d);
        if (scoreCompare != 0) return scoreCompare;

        final aMs = a.createdAt?.millisecondsSinceEpoch ?? 0;
        final bMs = b.createdAt?.millisecondsSinceEpoch ?? 0;
        return bMs.compareTo(aMs);
      });
    } else {
      current.sort((a, b) {
        final aMs = a.createdAt?.millisecondsSinceEpoch ?? 0;
        final bMs = b.createdAt?.millisecondsSinceEpoch ?? 0;
        return bMs.compareTo(aMs);
      });
    }

    _postsByTab[tab] = current;
  }

  void _applyOptimisticPostLike({
    required String postId,
    required bool willLike,
  }) {
    for (final tab in tabs) {
      final current = _postsByTab[tab];
      if (current == null || current.isEmpty) continue;

      final index = current.indexWhere((post) => post.postId == postId);
      if (index == -1) continue;

      final target = current[index];
      final nextLikeCount = willLike
          ? target.likeCount + 1
          : (target.likeCount > 0 ? target.likeCount - 1 : 0);
      final nextScore7d = willLike
          ? target.score7d + 1
          : (target.score7d > 0 ? target.score7d - 1 : 0);

      current[index] = target.copyWith(
        likeCount: nextLikeCount,
        score7d: nextScore7d,
        updatedAt: DateTime.now(),
      );

      _sortPostsForTab(tab);
    }
  }

  void _revertOptimisticPostLike({
    required String postId,
    required bool willLike,
  }) {
    _applyOptimisticPostLike(postId: postId, willLike: !willLike);
  }

  Future<void> togglePostLike({
    required String postId,
    required String userId,
    required bool isCurrentlyLiked,
  }) async {
    final willLike = !isCurrentlyLiked;

    _applyOptimisticPostLike(postId: postId, willLike: willLike);
    notifyListeners();

    try {
      await _repository.togglePostLike(postId: postId, userId: userId);
    } catch (e) {
      _revertOptimisticPostLike(postId: postId, willLike: willLike);
      notifyListeners();

      debugPrint(
        'CommunityProvider togglePostLike error: ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  Future<PostModel?> fetchPostDetail(String postId) async {
    try {
      return await _repository.fetchPostDetail(postId);
    } catch (e) {
      debugPrint(
        'CommunityProvider fetchPostDetail error: ${PrivacyLogUtils.errorSummary(e)}',
      );
      return null;
    }
  }

  Future<void> deletePost({required String postId}) async {
    try {
      await _repository.softDeletePost(postId: postId);
      await _reloadLoadedTabs();
    } catch (e) {
      debugPrint(
        'CommunityProvider deletePost error: ${PrivacyLogUtils.errorSummary(e)}',
      );
      rethrow;
    }
  }

  /// 대나무숲 글 신고. 서버가 신고자에게서 그 글을 숨기므로 목록을 다시 읽는다.
  Future<void> reportPost({
    required String postId,
    required String reason,
  }) async {
    await _repository.reportContent(
      contentType: 'bamboo_post',
      postId: postId,
      reason: reason,
    );
    await _reloadLoadedTabs();
  }

  Future<void> _reloadLoadedTabs() async {
    for (final tab in tabs) {
      if ((_postsByTab[tab] ?? []).isNotEmpty || tab == _selectedTab) {
        await loadPosts(tab: tab, forceRefresh: true);
      }
    }
  }

  PostModel? findPostById(String postId) {
    for (final tab in tabs) {
      final post = (_postsByTab[tab] ?? []).cast<PostModel?>().firstWhere(
        (p) => p?.postId == postId,
        orElse: () => null,
      );
      if (post != null) return post;
    }
    return null;
  }
}
