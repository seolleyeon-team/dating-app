// Source contract for the list queries behind the notification, asks and
// likes screens: each one is bounded, the filters the Firestore rules require
// are still there, and the screens no longer build the stream in `build()`.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

/// The source of [name] up to the end of its first statement or block.
String _method(String source, String name) {
  final start = source.indexOf(RegExp('\\b${RegExp.escape(name)}\\('));
  expect(start, isNonNegative, reason: '$name not found');
  final next = source.indexOf('\n  }\n', start);
  expect(next, isNonNegative, reason: '$name has no end');
  return source.substring(start, next);
}

void main() {
  test('the notification list and badge queries are bounded', () {
    final source = _read(
      'lib/features/notifications/services/notification_service.dart',
    );

    final list = _method(source, 'notificationsStream');
    expect(list, contains(".orderBy('createdAt', descending: true)"));
    expect(list, contains('.limit(limit)'));
    expect(list, contains('int limit = pageSize'));

    final badge = _method(source, 'unreadNotificationCountStream');
    expect(badge, contains(".where('isRead', isEqualTo: false)"));
    expect(badge, contains('.limit(unreadCountCap)'));
  });

  test('the asks inbox and badge queries are bounded', () {
    final source = _read('lib/services/ask_service.dart');

    final received = _method(source, 'receivedAsksStream');
    expect(received, contains(".where('toUserId', isEqualTo: userId)"));
    expect(received, contains('.limit(limit)'));

    final sent = _method(source, 'sentAsksStream');
    expect(sent, contains(".where('fromUserId', isEqualTo: userId)"));
    expect(sent, contains('.limit(limit)'));

    final badge = _method(source, 'unreadReceivedCount');
    expect(badge, contains(".where('status', isEqualTo: 'sent')"));
    expect(badge, contains('.limit(unreadCountCap)'));
  });

  test(
    'the like queries are bounded and keep the filter the rules require',
    () {
      final source = _read('lib/services/interaction_service.dart');

      for (final entry in {
        'getLikesReceived': 'toUserId',
        'watchLikesReceived': 'toUserId',
        'getLikesSent': 'fromUserId',
        'watchLikesSent': 'fromUserId',
      }.entries) {
        final method = _method(source, entry.key);
        expect(
          method,
          contains(".where('${entry.value}', isEqualTo: userId)"),
          reason: entry.key,
        );
        // The `interactions` list rule only admits a like query.
        expect(
          method,
          contains(".where('action', whereIn: ['like', 'super_like'])"),
          reason: entry.key,
        );
        expect(
          method,
          contains(".orderBy('createdAt', descending: true)"),
          reason: entry.key,
        );
        expect(method, contains('.limit(limit)'), reason: entry.key);
      }
    },
  );

  test('every bounded query shape is served by an existing composite index', () {
    final indexes = _read(
      'firestore.indexes.json',
    ).replaceAll(RegExp(r'\s+'), '');
    String index(String group, List<(String, String)> fields) =>
        '"collectionGroup":"$group","queryScope":"COLLECTION","fields":['
        '${fields.map((f) => '{"fieldPath":"${f.$1}","order":"${f.$2}"}').join(',')}'
        ']';

    for (final shape in [
      index('asks', [('toUserId', 'ASCENDING'), ('createdAt', 'DESCENDING')]),
      index('asks', [('fromUserId', 'ASCENDING'), ('createdAt', 'DESCENDING')]),
      index('asks', [('toUserId', 'ASCENDING'), ('status', 'ASCENDING')]),
      index('interactions', [
        ('toUserId', 'ASCENDING'),
        ('action', 'ASCENDING'),
        ('createdAt', 'DESCENDING'),
      ]),
      index('interactions', [
        ('fromUserId', 'ASCENDING'),
        ('action', 'ASCENDING'),
        ('createdAt', 'DESCENDING'),
      ]),
    ]) {
      expect(indexes, contains(shape));
    }
  });

  test('the screens do not create these streams in build()', () {
    final createdInBuild = RegExp(
      r'stream:\s*(?:_userId == null\s*\?\s*null\s*:\s*)?'
      r'_(?:notificationService|askService|interactionService)\s*\.',
    );
    for (final path in [
      'lib/features/notifications/screens/notification_list_screen.dart',
      'lib/features/profile/screens/asks_inbox_screen.dart',
      'lib/features/profile/screens/my_page_screen.dart',
      'lib/features/matching/screens/mystery_card_screen.dart',
      'lib/features/profile/screens/received_hearts_screen.dart',
      'lib/features/matching/screens/sent_hearts_screen.dart',
    ]) {
      final source = _read(path);
      expect(createdInBuild.hasMatch(source), isFalse, reason: path);
      expect(
        source,
        isNot(contains('future: _hydrate(interactions)')),
        reason: path,
      );
    }
    final home = _read(
      'lib/features/matching/screens/mystery_card_screen.dart',
    );
    expect(home, contains('_unreadNotificationStream.of('));
    expect(home, contains('_heartBalanceStream.of('));
    expect(home, contains('_unreadAsksStream.of('));
  });
}
