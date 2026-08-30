import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// SEC-04 Phase A.
///
/// 대나무숲 글/댓글에 raw UID 가 public `authorId` 로 남아 있고
/// `publicProfiles/{uid}` 는 로그인만 하면 읽힌다. join 한 번이면 익명 글의
/// 작성자를 특정할 수 있다는 뜻이라, 최종적으로는 public 에서 authorId 를
/// 지워야 한다. 그때 "내가 쓴 글" 을 잃지 않으려면 소유권이 미리 비공개
/// 매핑에 들어와 있어야 한다.
///
/// 이 저장소에는 Firestore 를 흉내내는 테스트 기반이 없어서, 다른 보안 회귀
/// 테스트와 같은 방식으로 소스 계약을 고정한다.
void main() {
  final source = File(
    'lib/data/repositories/firestore_community_repository.dart',
  ).readAsStringSync();

  test('글은 소유권 매핑과 한 번에 커밋된다', () {
    // 따로 쓰면 둘 중 하나만 성공한 상태가 생기고, 나중에 public authorId 를
    // 지울 때 주인 없는 글이 된다.
    expect(source.contains("collection('bamboo_post_authors')"), isTrue);
    expect(
      source.contains('_firestore.batch()'),
      isTrue,
      reason: 'post and ownership mapping must be written atomically',
    );
    expect(
      RegExp(r'batch\.set\(_postAuthors\.doc\(').hasMatch(source),
      isTrue,
      reason: 'the mapping must be part of the same batch as the post',
    );
    expect(
      source.contains('await docRef.set({'),
      isFalse,
      reason: 'a standalone post write would leave the mapping behind',
    );
  });

  test('댓글은 소유권 매핑과 같은 트랜잭션에서 커밋된다', () {
    expect(source.contains("collection('bamboo_comment_authors')"), isTrue);
    expect(
      // 포맷터가 줄을 바꿀 수 있으므로 공백에 관대하게 본다.
      RegExp(
        r'transaction\s*\.set\(\s*_commentAuthors\.doc\(',
      ).hasMatch(source),
      isTrue,
      reason: 'the comment mapping must ride the comment transaction',
    );
  });

  test('댓글 매핑 id 는 글 id 를 포함한다', () {
    // commentId 는 글 안에서만 유일하다. 글 id 를 빼면 다른 글의 댓글끼리
    // 매핑이 충돌한다.
    expect(source.contains(r"'${postId}__$commentId'"), isTrue);
  });

  test('매핑에는 ownerUid 만 담고 public authorId 를 중복해 넣지 않는다', () {
    expect(source.contains("'ownerUid': authorIdStr"), isTrue);
    expect(
      source.contains("'authorId': authorIdStr,\n      'ownerUid'"),
      isFalse,
      reason: 'the private mapping must not duplicate the public identity',
    );
  });

  test('Phase A 는 public authorId 를 아직 지우지 않는다', () {
    // 구버전 앱이 아직 이 필드로 "내가 쓴 글" 을 찾는다. 여기서 지우면
    // 업데이트하지 않은 사용자의 글 목록이 빈다.
    expect(source.contains("'authorId': authorIdStr"), isTrue);
    expect(source.contains("'authorId': authorId,"), isTrue);
    expect(
      source.contains(".where('authorId', isEqualTo: uid)"),
      isTrue,
      reason: 'Phase A keeps the legacy my-posts query',
    );
  });
}
