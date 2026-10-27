import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// P0-3 / SEC-04 — 대나무숲 클라이언트 소스 계약.
///
/// (이전 Phase A 계약 — 클라이언트가 public authorId 와 매핑을 같이 쓴다 — 은
/// 글/댓글 작성이 서버 callable 로 옮겨지면서 이미 사실이 아니었다. 이 파일은
/// 최종 계약으로 바뀌었다.)
///
/// public 대나무숲 문서에는 작성자가 없다. 클라이언트는 작성자 UID 를 읽지도,
/// 쓰지도, 서버에 보내지도 않는다. "내 글" 은 본인만 읽을 수 있는 비공개 매핑으로만
/// 알고, 삭제·신고는 서버 callable 이 매핑으로 판정한다. 이 저장소에는 Firestore
/// 를 흉내내는 테스트 기반이 없어 다른 보안 회귀 테스트처럼 소스 계약을 고정한다.
void main() {
  String read(String path) => File(path).readAsStringSync();
  String code(String path) => read(
    path,
  ).split('\n').where((line) => !line.trimLeft().startsWith('//')).join('\n');

  final repo = code(
    'lib/data/repositories/firestore_community_repository.dart',
  );
  final iface = code('lib/data/repositories/community_repository.dart');
  final model = code('lib/data/models/community/post_model.dart');
  final provider = code(
    'lib/features/community/providers/community_provider.dart',
  );
  final screens = [
    code('lib/features/community/screens/community_screen.dart'),
    code('lib/features/community/screens/post_detail_screen.dart'),
    code('lib/features/community/screens/post_write_screen.dart'),
    code('lib/features/community/widgets/community_report_block_flow.dart'),
  ].join('\n');

  test('어떤 대나무숲 클라이언트 코드도 authorId 를 읽거나 쓰지 않는다', () {
    for (final entry in {
      'repository': repo,
      'interface': iface,
      'model': model,
      'provider': provider,
      'screens': screens,
    }.entries) {
      expect(entry.value.contains('authorId'), isFalse, reason: entry.key);
    }
  });

  test('"내가 쓴 글" 은 비공개 매핑(ownerUid == 본인)으로만 찾는다', () {
    expect(repo.contains("'bamboo_post_authors'"), isTrue);
    expect(
      RegExp(
        r"_postAuthors\s*\.where\('ownerUid', isEqualTo: uid\)",
      ).hasMatch(repo),
      isTrue,
    );
    expect(
      repo.contains(
        "_commentAuthors\n        .where('ownerUid', isEqualTo: uid)",
      ),
      isTrue,
    );
  });

  test('작성·삭제·신고는 서버 callable 로만 한다', () {
    for (final callable in [
      'createCommunityPost',
      'createCommunityComment',
      'deleteCommunityPost',
      'deleteCommunityComment',
      'reportBambooContent',
    ]) {
      expect(
        repo.contains("httpsCallable('$callable')"),
        isTrue,
        reason: callable,
      );
    }
    // 클라이언트가 isDeleted 를 직접 쓰지 않는다 (rules 도 거부한다).
    expect(repo.contains("'isDeleted': true"), isFalse);
    expect(repo.contains("'commentCount'"), isFalse);
  });

  test('실명 차단 목록으로 익명 글을 거르지 않고, 신고가 실명 차단을 만들지 않는다', () {
    // "누군가를 차단하고 어떤 글이 사라지는지 본다" 는 작성자 특정 오라클이 된다.
    expect(repo.contains('ContactBlockService'), isFalse);
    expect(repo.contains('getBlockedUserIds'), isFalse);
    expect(screens.contains('blockAndReportUser'), isFalse);
    expect(screens.contains('reportedUserId'), isFalse);
    expect(repo.contains('bambooHiddenContent'), isTrue);
  });

  test('좋아요는 로그인한 본인 이름으로만 쓰고 읽는다', () {
    expect(
      RegExp(r"userId\.trim\(\) != _uid").allMatches(repo).length,
      greaterThanOrEqualTo(4),
      reason:
          'toggle/hasLiked for posts and comments are bound to the session uid',
    );
  });

  test('provider 는 계정이 바뀌면 캐시를 버린다', () {
    expect(provider.contains('_resetIfAccountChanged'), isTrue);
    expect(provider.contains('_myPostIds.clear()'), isTrue);
  });
}
