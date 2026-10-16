import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/models/chat_room_unread.dart';
import 'package:seolleyeon/features/chat/providers/chat_unread_provider.dart';

typedef RoomRow = MapEntry<String, Map<String, dynamic>?>;

RoomRow room(String id, {Map<String, dynamic>? data}) => RoomRow(id, data);

Map<String, dynamic> modelRoom(Map<String, num> counts) => {
  'unreadModelVersion': 1,
  'unreadCounts': counts,
};

void main() {
  group('ChatRoomUnread.fromRoomData (behavior contract)', () {
    test('reads the current user counter from a modelled room', () {
      final state = ChatRoomUnread.fromRoomData(
        'r',
        modelRoom({'me': 3, 'peer': 0}),
        'me',
      );
      expect(state.hasUnreadModel, isTrue);
      expect(state.unreadCount, 3);
      expect(state.hasUnread, isTrue);
    });

    test('another participant counter never leaks into mine', () {
      final state = ChatRoomUnread.fromRoomData(
        'r',
        modelRoom({'peer': 9}),
        'me',
      );
      expect(state.unreadCount, 0);
      expect(state.hasUnread, isFalse);
    });

    test('legacy room without the model reports no unread and never scans', () {
      // TEST P0-2-J: new client + legacy room must not crash and must not
      // fall back to reading message history.
      final legacy = ChatRoomUnread.fromRoomData('r', {
        'lastMessage': 'hi',
        'participantIds': ['me', 'peer'],
      }, 'me');
      expect(legacy.hasUnreadModel, isFalse);
      expect(legacy.unreadCount, 0);
      expect(ChatRoomUnread.fromRoomData('r', null, 'me').hasUnread, isFalse);
    });

    test('malformed counters are treated as zero, never as a crash', () {
      expect(
        ChatRoomUnread.fromRoomData(
          'r',
          modelRoom({'me': -4}),
          'me',
        ).unreadCount,
        0,
      );
      expect(
        ChatRoomUnread.fromRoomData('r', {
          'unreadModelVersion': 1,
          'unreadCounts': 'junk',
        }, 'me').unreadCount,
        0,
      );
      expect(
        ChatRoomUnread.fromRoomData('r', {
          'unreadModelVersion': 1,
          'unreadCounts': {'me': '7'},
        }, 'me').unreadCount,
        0,
      );
      expect(
        ChatRoomUnread.fromRoomData('r', {
          'unreadModelVersion': 2,
          'unreadCounts': {'me': 7},
        }, 'me').hasUnreadModel,
        isFalse,
        reason: 'an unknown model version is not trusted',
      );
    });
  });

  group('ChatUnreadProvider', () {
    late StreamController<List<RoomRow>> controller;
    late int subscriptions;
    late List<String> boundUsers;

    ChatUnreadProvider makeProvider() {
      return ChatUnreadProvider(
        roomsSource: (uid) {
          subscriptions += 1;
          boundUsers.add(uid);
          return controller.stream;
        },
      );
    }

    setUp(() {
      controller = StreamController<List<RoomRow>>.broadcast();
      subscriptions = 0;
      boundUsers = [];
    });

    tearDown(() async {
      await controller.close();
    });

    test('one subscription serves the badge and every room row', () async {
      final provider = makeProvider();
      var notifications = 0;
      provider.addListener(() => notifications++);
      provider.bindUser('me');
      provider.bindUser('me'); // idempotent
      expect(subscriptions, 1);

      controller.add([
        room('a', data: modelRoom({'me': 2})),
        room('b', data: modelRoom({'me': 0})),
        room('legacy'),
      ]);
      await Future<void>.delayed(Duration.zero);

      expect(provider.hasAnyUnread, isTrue);
      expect(provider.unreadCountFor('a'), 2);
      expect(provider.isRoomUnread('a'), isTrue);
      expect(provider.isRoomUnread('b'), isFalse);
      expect(provider.isRoomUnread('legacy'), isFalse);
      expect(provider.summary.roomCount, 3);
      expect(notifications, greaterThanOrEqualTo(2));
      expect(subscriptions, 1, reason: 'no re-subscription on updates');

      controller.add([
        room('a', data: modelRoom({'me': 0})),
      ]);
      await Future<void>.delayed(Duration.zero);
      expect(provider.hasAnyUnread, isFalse);
      provider.dispose();
    });

    test(
      'logout clears state and cancels the subscription; a new user starts clean',
      () async {
        final provider = makeProvider();
        provider.bindUser('alice');
        controller.add([
          room('a', data: modelRoom({'alice': 5})),
        ]);
        await Future<void>.delayed(Duration.zero);
        expect(provider.hasAnyUnread, isTrue);

        provider.bindUser(null);
        expect(provider.userId, isNull);
        expect(provider.hasAnyUnread, isFalse);
        expect(provider.summary.roomCount, 0);

        // Late events from the old stream must not resurrect the old state.
        controller.add([
          room('a', data: modelRoom({'alice': 5})),
        ]);
        await Future<void>.delayed(Duration.zero);
        expect(provider.hasAnyUnread, isFalse);

        provider.bindUser('bob');
        expect(boundUsers, ['alice', 'bob']);
        expect(provider.hasAnyUnread, isFalse);
        controller.add([
          room('b', data: modelRoom({'bob': 1, 'alice': 9})),
        ]);
        await Future<void>.delayed(Duration.zero);
        expect(
          provider.unreadCountFor('b'),
          1,
          reason: "alice's counter is not bob's",
        );
        provider.dispose();
      },
    );

    test(
      'a stream error fails closed (no badge) and is retained for diagnostics',
      () async {
        final provider = makeProvider();
        provider.bindUser('me');
        controller.add([
          room('a', data: modelRoom({'me': 1})),
        ]);
        await Future<void>.delayed(Duration.zero);
        expect(provider.hasAnyUnread, isTrue);
        controller.addError(StateError('permission-denied'));
        await Future<void>.delayed(Duration.zero);
        expect(provider.hasAnyUnread, isFalse);
        expect(provider.lastError, isA<StateError>());
        provider.dispose();
      },
    );

    test(
      'dispose cancels and later events are ignored without throwing',
      () async {
        final provider = makeProvider();
        provider.bindUser('me');
        provider.dispose();
        controller.add([
          room('a', data: modelRoom({'me': 1})),
        ]);
        await Future<void>.delayed(Duration.zero);
        expect(controller.hasListener, isFalse);
      },
    );
  });
}
