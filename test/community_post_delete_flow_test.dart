import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/community/widgets/community_post_delete_flow.dart';

void main() {
  group('isCommunityPostOwner', () {
    test('supports a legacy numeric Kakao app user id', () {
      expect(
        isCommunityPostOwner(
          currentUserId: '1234567890',
          authorId: '1234567890',
        ),
        isTrue,
      );
    });

    test('supports a new primary-email Firebase uid', () {
      expect(
        isCommunityPostOwner(
          currentUserId: 'firebase-email-uid',
          authorId: 'firebase-email-uid',
        ),
        isTrue,
      );
    });

    test('rejects missing or different identities', () {
      expect(
        isCommunityPostOwner(currentUserId: null, authorId: 'writer'),
        isFalse,
      );
      expect(
        isCommunityPostOwner(currentUserId: 'reader', authorId: 'writer'),
        isFalse,
      );
    });
  });

  testWidgets('delete requires both menu selection and confirmation', (
    tester,
  ) async {
    bool? result;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            onPressed: () async {
              result = await confirmCommunityPostDeletion(context);
            },
            child: const Text('더보기'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('더보기'));
    await tester.pumpAndSettle();
    expect(find.text('게시글 삭제'), findsOneWidget);
    expect(result, isNull);

    await tester.tap(
      find.byKey(const ValueKey('community-post-delete-action')),
    );
    await tester.pumpAndSettle();
    expect(find.text('게시글을 삭제할까요?'), findsOneWidget);
    expect(result, isNull);

    await tester.tap(
      find.byKey(const ValueKey('community-post-delete-confirm')),
    );
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });
}
