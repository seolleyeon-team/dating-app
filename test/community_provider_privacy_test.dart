import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/data/models/community/post_model.dart';
import 'package:seolleyeon/data/repositories/community_repository.dart';
import 'package:seolleyeon/features/community/providers/community_provider.dart';

/// P0-3 — 대나무숲 provider: "내 글" 은 비공개 매핑 조회로만 알고, 계정이 바뀌면
/// 이전 계정의 목록과 "내 글" 표시가 남지 않는다 (ATTACK 16).
PostModel _post(String id) => PostModel.empty().copyWith(
  postId: id,
  content: 'c-$id',
  category: '고민',
  createdAt: DateTime(2026, 10, 1),
);

class _FakeRepo implements CommunityRepository {
  _FakeRepo(this.uid);

  String Function() uid;
  final Map<String, List<String>> feedByUid = {};
  final Map<String, Set<String>> ownedByUid = {};
  final List<String> calls = [];

  @override
  Future<CommunityPostPage> fetchPostsPage({
    required String tab,
    int limit = 5,
    Object? cursor,
  }) async {
    final who = uid();
    calls.add('page:$tab:$who');
    final ids = tab == CommunityProvider.myPostsTab
        ? (ownedByUid[who] ?? {}).toList()
        : (feedByUid['*'] ?? const []);
    return CommunityPostPage(
      posts: ids.map(_post).toList(),
      cursor: null,
      hasMore: false,
    );
  }

  @override
  Future<Set<String>> fetchMyPostIds(Iterable<String> postIds) async {
    calls.add('owned:${uid()}');
    final mine = ownedByUid[uid()] ?? {};
    return postIds.where(mine.contains).toSet();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  _accountSwitchDuringOwnershipLookup();
  test('isMine 은 매핑 조회 결과로만 정해진다 (모델에는 작성자가 없다)', () async {
    var who = 'alice';
    final repo = _FakeRepo(() => who)
      ..feedByUid['*'] = ['p1', 'p2']
      ..ownedByUid['alice'] = {'p2'};
    final provider = CommunityProvider(repository: repo, currentUid: () => who);

    await provider.initialize();
    expect(provider.posts.map((p) => p.postId), ['p1', 'p2']);
    expect(provider.isMine('p1'), isFalse);
    expect(provider.isMine('p2'), isTrue);
    expect(
      repo.calls.where((c) => c.startsWith('owned:')).length,
      1,
      reason: 'one bounded ownership query per page, not one per post',
    );
  });

  test('ATTACK 16: 계정이 바뀌면 이전 계정의 내 글 목록과 표시가 사라진다', () async {
    var who = 'alice';
    final repo = _FakeRepo(() => who)
      ..feedByUid['*'] = ['p1', 'p2']
      ..ownedByUid['alice'] = {'p1'}
      ..ownedByUid['bob'] = {};
    final provider = CommunityProvider(repository: repo, currentUid: () => who);

    await provider.initialize();
    await provider.changeTab(CommunityProvider.myPostsTab);
    expect(provider.posts.map((p) => p.postId), ['p1']);
    expect(provider.isMine('p1'), isTrue);

    who = 'bob';
    // 화면이 다시 열리면 initialize 가 계정 변경을 감지하고 처음부터 읽는다.
    await provider.initialize();
    expect(provider.isMine('p1'), isFalse);
    expect(provider.postsOf(CommunityProvider.myPostsTab), isEmpty);
    await provider.changeTab(CommunityProvider.myPostsTab);
    expect(provider.posts, isEmpty);
    expect(repo.calls.last, 'page:${CommunityProvider.myPostsTab}:bob');
  });

  test('P1-4: 인증 변경(bindUser) 은 다음 피드 요청 전에 이전 계정의 캐시를 비우고 알린다', () async {
    var who = 'alice';
    final repo = _FakeRepo(() => who)
      ..feedByUid['*'] = ['p1', 'p2']
      ..ownedByUid['alice'] = {'p1'}
      ..ownedByUid['bob'] = {};
    final provider = CommunityProvider(repository: repo, currentUid: () => who);
    provider.bindUser('alice');
    await provider.initialize();
    await provider.changeTab(CommunityProvider.myPostsTab);
    expect(provider.posts.map((p) => p.postId), ['p1']);
    expect(provider.isMine('p1'), isTrue);
    final callsBefore = repo.calls.length;

    // 로그아웃: 요청 없이도 즉시 비어야 한다.
    var notified = 0;
    provider.addListener(() => notified++);
    who = '';
    provider.bindUser(null);
    expect(notified, 1);
    expect(provider.posts, isEmpty);
    expect(provider.postsOf('전체'), isEmpty);
    expect(provider.isMine('p1'), isFalse);
    expect(repo.calls.length, callsBefore, reason: '비우기는 네트워크를 타지 않는다');

    // bob 로그인: 여전히 비어 있고, 다음 initialize 는 bob 으로 읽는다.
    who = 'bob';
    provider.bindUser('bob');
    expect(notified, 2);
    expect(provider.posts, isEmpty);
    expect(provider.isMine('p1'), isFalse);
    await provider.initialize();
    expect(repo.calls.last, 'page:${CommunityProvider.myPostsTab}:bob');
    expect(provider.isMine('p1'), isFalse);

    // 같은 계정으로 다시 bind 하면 아무 일도 없다 (알림도, 비우기도 없다).
    final notifiedBefore = notified;
    provider.bindUser('bob');
    expect(notified, notifiedBefore);
    expect(repo.calls.last, 'page:${CommunityProvider.myPostsTab}:bob');
  });

  test('응답을 기다리는 사이 계정이 바뀌면 그 응답은 버린다', () async {
    var who = 'alice';
    final repo = _SlowRepo(() => who, onFetch: () => who = 'bob');
    final provider = CommunityProvider(repository: repo, currentUid: () => who);
    await provider.loadPosts(
      tab: CommunityProvider.myPostsTab,
      forceRefresh: true,
    );
    expect(provider.postsOf(CommunityProvider.myPostsTab), isEmpty);
    expect(provider.isMine('alice-secret'), isFalse);
  });
}

class _SlowRepo extends _FakeRepo {
  _SlowRepo(super.uid, {required this.onFetch});
  final void Function() onFetch;

  @override
  Future<CommunityPostPage> fetchPostsPage({
    required String tab,
    int limit = 5,
    Object? cursor,
  }) async {
    // alice 의 페이지를 받아 오는 동안 로그아웃 → bob 로그인
    onFetch();
    return CommunityPostPage(
      posts: [_post('alice-secret')],
      cursor: null,
      hasMore: false,
    );
  }
}

class _SwitchDuringOwnershipRepo extends _FakeRepo {
  _SwitchDuringOwnershipRepo(super.uid, {required this.onOwnership});
  final void Function() onOwnership;

  @override
  Future<Set<String>> fetchMyPostIds(Iterable<String> postIds) async {
    // A 의 소유 조회가 끝나기 전에 B 로 전환된다.
    final mine = await super.fetchMyPostIds(postIds);
    onOwnership();
    return mine;
  }
}

void _accountSwitchDuringOwnershipLookup() {
  test('리뷰 L4: 소유 조회 도중 계정이 바뀌면 이전 계정의 목록·내 글 표시를 넣지 않는다', () async {
    var who = 'alice';
    final repo =
        _SwitchDuringOwnershipRepo(() => who, onOwnership: () => who = 'bob')
          ..feedByUid['*'] = ['p1']
          ..ownedByUid['alice'] = {'p1'};
    final provider = CommunityProvider(repository: repo, currentUid: () => who);
    await provider.loadPosts(tab: '전체', forceRefresh: true);
    expect(provider.isMine('p1'), isFalse);
    expect(provider.postsOf('전체'), isEmpty);
  });
}
