import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/growing_query_window.dart';
import 'package:seolleyeon/shared/utils/keyed_stream.dart';

/// Counts how often a source is asked for a stream and how many listeners
/// that produced, the way a Firestore `snapshots()` call would be billed.
class _Source {
  int created = 0;
  int listens = 0;
  int cancels = 0;

  Stream<int> watch(String uid) {
    created += 1;
    late final StreamController<int> controller;
    controller = StreamController<int>(
      onListen: () {
        listens += 1;
        controller.add(uid.length);
      },
      onCancel: () => cancels += 1,
    );
    return controller.stream;
  }
}

class _Host extends StatefulWidget {
  const _Host({required this.source, required this.hoisted});

  final _Source source;
  final bool hoisted;

  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  final _stream = KeyedStream<String, int>();
  String uid = 'user-a';

  void rebuild() => setState(() {});
  void switchUser(String next) => setState(() => uid = next);

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<int>(
      stream: widget.hoisted
          ? _stream.of(uid, () => widget.source.watch(uid))
          : widget.source.watch(uid),
      builder: (context, snapshot) =>
          Text('${snapshot.data ?? '-'}', textDirection: TextDirection.ltr),
    );
  }
}

void main() {
  group('a stream created in build()', () {
    testWidgets('is reopened by every rebuild', (tester) async {
      final source = _Source();
      await tester.pumpWidget(_Host(source: source, hoisted: false));
      final state = tester.state<_HostState>(find.byType(_Host));

      for (var i = 0; i < 5; i++) {
        state.rebuild();
        await tester.pump();
      }

      expect(source.listens, 6, reason: 'one listener per build');
      expect(source.cancels, 5);
    });

    testWidgets('kept by KeyedStream is opened once and follows the user id', (
      tester,
    ) async {
      final source = _Source();
      await tester.pumpWidget(_Host(source: source, hoisted: true));
      final state = tester.state<_HostState>(find.byType(_Host));

      for (var i = 0; i < 5; i++) {
        state.rebuild();
        await tester.pump();
      }

      expect(source.created, 1);
      expect(source.listens, 1);
      expect(source.cancels, 0);

      // A stream that depends on the user id must not outlive that user.
      state.switchUser('user-bb');
      await tester.pump();
      await tester.pump();

      expect(source.created, 2);
      expect(source.listens, 2);
      expect(source.cancels, 1, reason: 'the previous user is unsubscribed');
      expect(find.text('7'), findsOneWidget);
    });
  });

  group('KeyedStream', () {
    test('compares record keys by value', () {
      final keyed = KeyedStream<(String, int), int>();
      var created = 0;
      Stream<int> create() {
        created += 1;
        return Stream<int>.fromIterable([created]);
      }

      final first = keyed.of(('u', 50), create);
      expect(identical(keyed.of(('u', 50), create), first), isTrue);
      expect(identical(keyed.of(('u', 100), create), first), isFalse);
      expect(created, 2);
    });
  });

  group('SourceFuture', () {
    test('starts one future per source object', () async {
      final hydration = SourceFuture<List<int>, int>();
      var runs = 0;
      Future<int> run(List<int> source) async {
        runs += 1;
        return source.length;
      }

      final snapshot = [1, 2, 3];
      final first = hydration.of(snapshot, () => run(snapshot));
      for (var i = 0; i < 4; i++) {
        expect(
          identical(hydration.of(snapshot, () => run(snapshot)), first),
          isTrue,
        );
      }
      expect(await first, 3);
      expect(runs, 1);

      // An equal but new list is a new snapshot.
      final next = [1, 2, 3];
      await hydration.of(next, () => run(next));
      expect(runs, 2);
    });
  });

  group('GrowingQueryWindow', () {
    test('grows only at the end of a full window', () {
      final window = GrowingQueryWindow(pageSize: 50);
      expect(window.limit, 50);

      // Not at the end.
      expect(window.growIfNeeded(loadedCount: 50, extentAfter: 900), isFalse);
      // At the end, but the window is not full: nothing older exists.
      expect(window.growIfNeeded(loadedCount: 31, extentAfter: 0), isFalse);
      expect(window.limit, 50);

      expect(window.growIfNeeded(loadedCount: 50, extentAfter: 10), isTrue);
      expect(window.limit, 100);

      // The wider snapshot has not arrived yet: further scroll notifications
      // must not widen the window again.
      expect(window.growIfNeeded(loadedCount: 50, extentAfter: 0), isFalse);
      expect(window.limit, 100);

      expect(window.growIfNeeded(loadedCount: 100, extentAfter: 0), isTrue);
      expect(window.limit, 150);
    });
  });
}
