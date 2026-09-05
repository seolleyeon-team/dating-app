import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/profile_card_args.dart';
import 'package:seolleyeon/features/profile/widgets/friends_list_shared.dart';
import 'package:seolleyeon/router/route_names.dart';
import 'package:seolleyeon/services/friend_service.dart';

/// In-memory friend graph standing in for `users/{uid}/friends`.
///
/// After A invites B and B taps [친구 추가], the server writes BOTH edges in
/// one transaction (functions/src/friendInvites.ts). This double models that
/// post-accept state so the profile "친구" tab can be tested end to end
/// without Firestore.
class _GraphFriendService extends FriendService {
  _GraphFriendService(this.graph);

  final Map<String, List<FriendListItem>> graph;
  final Map<String, Set<StreamController<List<FriendListItem>>>> _live = {};

  /// Simulates a new friend edge landing (an accepted invite).
  void addEdge(String userId, FriendListItem item) {
    graph.putIfAbsent(userId, () => []).insert(0, item);
    for (final c
        in _live[userId] ?? const <StreamController<List<FriendListItem>>>{}) {
      c.add(List.of(graph[userId]!));
    }
  }

  @override
  Stream<List<FriendListItem>> watchFriendItems(String userId) {
    late final StreamController<List<FriendListItem>> controller;
    controller = StreamController<List<FriendListItem>>(
      onListen: () {
        _live.putIfAbsent(userId, () => {}).add(controller);
        controller.add(List.of(graph[userId] ?? const []));
      },
      onCancel: () => _live[userId]?.remove(controller),
    );
    return controller.stream;
  }

  @override
  Stream<int> watchFriendsCount(String userId) =>
      watchFriendItems(userId).map((items) => items.length);
}

FriendListItem _item(String uid, String name) => FriendListItem(
  friendUserId: uid,
  pairId: 'pair',
  createdAt: DateTime(2026, 9, 5),
  name: name,
  imageUrl: '',
  universityName: '연세대학교',
  major: '컴퓨터과학',
);

const _a = 'user_a';
const _b = 'user_b';

_GraphFriendService _mutualGraph() => _GraphFriendService({
  _a: [_item(_b, '비비')],
  _b: [_item(_a, '에이')],
});

Widget _host(Widget body, {RouteFactory? onGenerateRoute}) {
  return CupertinoApp(
    onGenerateRoute: onGenerateRoute,
    home: CupertinoPageScaffold(child: body),
  );
}

void main() {
  group('profile friend tab (users/{uid}/friends)', () {
    testWidgets('A sees B and B sees A after one accepted invite', (
      tester,
    ) async {
      final service = _mutualGraph();

      await tester.pumpWidget(
        _host(
          FriendsListStreamBody(
            currentUserId: _a,
            friendService: service,
            formatAddedAt: (_) => '',
          ),
        ),
      );
      await tester.pump();
      expect(find.text('비비'), findsOneWidget);
      expect(find.text('에이'), findsNothing);

      await tester.pumpWidget(
        _host(
          FriendsListStreamBody(
            currentUserId: _b,
            friendService: service,
            formatAddedAt: (_) => '',
          ),
        ),
      );
      await tester.pump();
      expect(find.text('에이'), findsOneWidget);
      expect(find.text('비비'), findsNothing);
    });

    test('friend count is the live edge count, +1 for each side', () async {
      final service = _GraphFriendService({});
      final countsA = <int>[];
      final countsB = <int>[];
      final subA = service.watchFriendsCount(_a).listen(countsA.add);
      final subB = service.watchFriendsCount(_b).listen(countsB.add);
      await Future<void>.delayed(Duration.zero);
      expect(countsA, [0]);
      expect(countsB, [0]);

      // B accepts A's invite → the server writes both edges.
      service.addEdge(_a, _item(_b, '비비'));
      service.addEdge(_b, _item(_a, '에이'));
      await Future<void>.delayed(Duration.zero);
      expect(countsA, [0, 1]);
      expect(countsB, [0, 1]);

      await subA.cancel();
      await subB.cancel();
    });

    testWidgets('list updates without a rebuild when the edge lands', (
      tester,
    ) async {
      final service = _GraphFriendService({});
      await tester.pumpWidget(
        _host(
          FriendsListStreamBody(
            currentUserId: _a,
            friendService: service,
            formatAddedAt: (_) => '',
          ),
        ),
      );
      await tester.pump();
      expect(find.text('아직 추가된 친구가 없어요'), findsOneWidget);

      service.addEdge(_a, _item(_b, '비비'));
      await tester.pump();
      expect(find.text('비비'), findsOneWidget);
      expect(find.text('아직 추가된 친구가 없어요'), findsNothing);
    });

    testWidgets('tapping the counterpart opens their profile screen', (
      tester,
    ) async {
      final service = _mutualGraph();
      RouteSettings? pushed;

      await tester.pumpWidget(
        _host(
          Builder(
            builder: (context) => FriendsListStreamBody(
              currentUserId: _a,
              friendService: service,
              formatAddedAt: (_) => '',
              onBrowseTap: (item) => openFriendProfile(context, item),
            ),
          ),
          onGenerateRoute: (settings) {
            pushed = settings;
            return CupertinoPageRoute<void>(
              settings: settings,
              builder: (_) => const Center(child: Text('profile')),
            );
          },
        ),
      );
      await tester.pump();

      await tester.tap(find.byKey(const ValueKey('friend_tile_$_b')));
      await tester.pumpAndSettle();

      expect(pushed?.name, RouteNames.profileSpecificDetail);
      final args = pushed?.arguments as ProfileCardArgs?;
      expect(args?.userId, _b);
      expect(args?.showActions, isFalse, reason: 'friend profile is read-only');
      expect(find.text('profile'), findsOneWidget);
    });

    testWidgets('browse mode never shows the picker-only empty state', (
      tester,
    ) async {
      final service = _mutualGraph();
      await tester.pumpWidget(
        _host(
          FriendsListStreamBody(
            currentUserId: _a,
            friendService: service,
            formatAddedAt: (_) => '',
            excludedFriendUserIds: const {_b},
          ),
        ),
      );
      await tester.pump();
      expect(find.text('아직 추가된 친구가 없어요'), findsOneWidget);
      expect(find.text('선택할 수 있는 친구가 없어요'), findsNothing);
    });

    testWidgets('stream error shows the retry message, not a crash', (
      tester,
    ) async {
      final service = _FailingFriendService();
      await tester.pumpWidget(
        _host(
          FriendsListStreamBody(
            currentUserId: _a,
            friendService: service,
            formatAddedAt: (_) => '',
          ),
        ),
      );
      await tester.pump();
      expect(find.text('친구 목록을 불러오지 못했어요'), findsOneWidget);
    });
  });

  test('a friend whose profile is gone is never shown as a raw uid', () {
    expect(FriendService.withdrawnFriendDisplayName, isNot(isEmpty));
    expect(FriendService.withdrawnFriendDisplayName, isNot(contains('user_')));
  });
}

class _FailingFriendService extends FriendService {
  @override
  Stream<List<FriendListItem>> watchFriendItems(String userId) =>
      Stream<List<FriendListItem>>.error(StateError('boom'));
}
