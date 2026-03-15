import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import '../../../data/models/community/post_model.dart';
import '../../../data/repositories/firestore_community_repository.dart';
import '../../../providers/auth_provider.dart';
import '../../../services/storage_service.dart';

class CommunityProvider extends ChangeNotifier {
  CommunityProvider({
    FirestoreCommunityRepository? repository,
    AuthProvider? authProvider,
  })  : _repository = repository ?? FirestoreCommunityRepository(),
        _authProvider = authProvider;

  final FirestoreCommunityRepository _repository;
  final StorageService _storageService = StorageService();
  final AuthProvider? _authProvider;

  String? _currentUserId;
  String _selectedTab = '전체';
  bool _isInitialized = false;

  static const List<String> tabs = [
    '전체',
    '인기',
    '설렘',
    '고민',
    '일상',
    '질문',
    '내가 쓴 글',
  ];

  final Map<String, List<PostModel>> _postsByTab = {
    for (final tab in tabs) tab: <PostModel>[],
  };

  final Map<String, DocumentSnapshot<Map<String, dynamic>>?> _lastDocByTab = {
    for (final tab in tabs) tab: null,
  };

  final Map<String, bool> _isLoadingByTab = {
    for (final tab in tabs) tab: false,
  };

  final Map<String, bool> _isLoadingMoreByTab = {
    for (final tab in tabs) tab: false,
  };

  final Map<String, bool> _hasMoreByTab = {for (final tab in tabs) tab: true};

  String get selectedTab => _selectedTab;
  bool get isInitialized => _isInitialized;
  String? get currentUserId => _currentUserId;

  List<PostModel> get posts => _postsByTab[_selectedTab] ?? const [];
  bool get isLoading => _isLoadingByTab[_selectedTab] ?? false;
  bool get isLoadingMore => _isLoadingMoreByTab[_selectedTab] ?? false;
  bool get hasMore => _hasMoreByTab[_selectedTab] ?? false;

  List<PostModel> postsOf(String tab) => _postsByTab[tab] ?? const [];
  bool isLoadingOf(String tab) => _isLoadingByTab[tab] ?? false;
  bool isLoadingMoreOf(String tab) => _isLoadingMoreByTab[tab] ?? false;
  bool hasMoreOf(String tab) => _hasMoreByTab[tab] ?? false;

  Future<void> initialize() async {
    if (_isInitialized) return;
    _isInitialized = true;

    _currentUserId = await _storageService.getKakaoUserId();
    debugPrint('CommunityProvider initialize currentUserId: $_currentUserId');

    await loadPosts(tab: _selectedTab, forceRefresh: true);
  }

  Future<void> _ensureCurrentUserId() async {
    if ((_currentUserId ?? '').trim().isNotEmpty) return;
    _currentUserId = await _storageService.getKakaoUserId();
    if ((_currentUserId ?? '').trim().isEmpty) {
      final fromAuth = _authProvider?.kakaoUserId;
      if ((fromAuth ?? '').trim().isNotEmpty) _currentUserId = fromAuth;
    }
    debugPrint('CommunityProvider ensured currentUserId: $_currentUserId');
  }

  Future<void> changeTab(String tab) async {
    if (!tabs.contains(tab)) return;

    _selectedTab = tab;
    notifyListeners();

    if (tab == '내가 쓴 글') {
      await _ensureCurrentUserId();
    }

    final hasLoaded = (_postsByTab[tab] ?? []).isNotEmpty;
    if (!hasLoaded) {
      await loadPosts(tab: tab, forceRefresh: true);
    }
  }

  Future<void> loadPosts({
    required String tab,
    bool forceRefresh = false,
  }) async {
    if (!tabs.contains(tab)) return;
    if ((_isLoadingByTab[tab] ?? false) && !forceRefresh) return;

    if (tab == '내가 쓴 글') {
      await _ensureCurrentUserId();
    }

    _isLoadingByTab[tab] = true;

    if (forceRefresh) {
      _postsByTab[tab] = [];
      _lastDocByTab[tab] = null;
      _hasMoreByTab[tab] = true;
    }

    notifyListeners();

    try {
      debugPrint(
        'CommunityProvider loadPosts tab=$tab currentUserId=$_currentUserId',
      );

      final snapshot = await _repository.fetchPostsSnapshot(
        tab: tab,
        currentUserId: _currentUserId,
        limit: 5,
        lastDocument: null,
      );

      final docs = snapshot.docs;
      final loadedPosts = docs.map(PostModel.fromFirestore).toList();

      _postsByTab[tab] = loadedPosts;
      _lastDocByTab[tab] = docs.isNotEmpty ? docs.last : null;
      _hasMoreByTab[tab] = docs.length == 5;
    } catch (e, st) {
      debugPrint('CommunityProvider loadPosts error: $e');
      debugPrintStack(stackTrace: st);
    } finally {
      _isLoadingByTab[tab] = false;
      notifyListeners();
    }
  }

  Future<void> loadMore({String? tab}) async {
    final targetTab = tab ?? _selectedTab;
    if (!tabs.contains(targetTab)) return;

    if (targetTab == '내가 쓴 글') {
      await _ensureCurrentUserId();
    }

    if (_isLoadingMoreByTab[targetTab] == true) return;
    if (_hasMoreByTab[targetTab] != true) return;

    final lastDoc = _lastDocByTab[targetTab];
    if (lastDoc == null) return;

    _isLoadingMoreByTab[targetTab] = true;
    notifyListeners();

    try {
      final snapshot = await _repository.fetchPostsSnapshot(
        tab: targetTab,
        currentUserId: _currentUserId,
        limit: 5,
        lastDocument: lastDoc,
      );

      final docs = snapshot.docs;
      final newPosts = docs.map(PostModel.fromFirestore).toList();

      final currentPosts = [...(_postsByTab[targetTab] ?? <PostModel>[])];
      currentPosts.addAll(newPosts);

      _postsByTab[targetTab] = currentPosts;
      _lastDocByTab[targetTab] = docs.isNotEmpty ? docs.last : lastDoc;
      _hasMoreByTab[targetTab] = docs.length == 5;
    } catch (e, st) {
      debugPrint('CommunityProvider loadMore error: $e');
      debugPrintStack(stackTrace: st);
    } finally {
      _isLoadingMoreByTab[targetTab] = false;
      notifyListeners();
    }
  }

  Future<String?> createPost({
    required String authorId,
    required String content,
    required String category,
    required List<String> tags,
  }) async {
    try {
      final postId = await _repository.createPost(
        authorId: authorId,
        content: content,
        category: category,
        tags: tags,
      );

      _currentUserId ??= authorId;

      await refreshAfterPostCreated(category: category);
      return postId;
    } catch (e, st) {
      debugPrint('CommunityProvider createPost error: $e');
      debugPrintStack(stackTrace: st);
      return null;
    }
  }

  Future<void> refreshAfterPostCreated({required String category}) async {
    await loadPosts(tab: '전체', forceRefresh: true);

    if (tabs.contains(category)) {
      await loadPosts(tab: category, forceRefresh: true);
    }

    await loadPosts(tab: '인기', forceRefresh: true);
    await loadPosts(tab: '내가 쓴 글', forceRefresh: true);
  }

  Future<void> refreshCurrentTab() async {
    await loadPosts(tab: _selectedTab, forceRefresh: true);
  }

  Future<void> togglePostLike({
    required String postId,
    required String userId,
  }) async {
    try {
      await _repository.togglePostLike(postId: postId, userId: userId);
      await refreshCurrentTab();
    } catch (e, st) {
      debugPrint('CommunityProvider togglePostLike error: $e');
      debugPrintStack(stackTrace: st);
    }
  }

  Future<PostModel?> fetchPostDetail(String postId) async {
    try {
      return await _repository.fetchPostDetail(postId);
    } catch (e, st) {
      debugPrint('CommunityProvider fetchPostDetail error: $e');
      debugPrintStack(stackTrace: st);
      return null;
    }
  }

  Future<void> deletePost({
    required String postId,
    required String authorId,
  }) async {
    try {
      await _repository.softDeletePost(postId: postId, authorId: authorId);

      for (final tab in tabs) {
        if ((_postsByTab[tab] ?? []).isNotEmpty || tab == _selectedTab) {
          await loadPosts(tab: tab, forceRefresh: true);
        }
      }
    } catch (e, st) {
      debugPrint('CommunityProvider deletePost error: $e');
      debugPrintStack(stackTrace: st);
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
