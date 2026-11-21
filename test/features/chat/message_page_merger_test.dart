import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/services/message_page_merger.dart';

class Msg {
  const Msg(this.id, this.t, {this.type = 'text', this.promiseId});
  final String id;
  final int? t;
  final String type;
  final String? promiseId;

  @override
  String toString() => id;
}

MessagePageMerger<Msg> merger({int pageSize = 3}) => MessagePageMerger<Msg>(
  pageSize: pageSize,
  idOf: (m) => m.id,
  createdAtMillisOf: (m) => m.t,
  typeOf: (m) => m.type,
  promiseIdOf: (m) => m.promiseId,
);

List<Msg> seq(int from, int to) => [
  for (var i = from; i <= to; i++) Msg('m$i', i * 1000),
];

void main() {
  group('MessagePageMerger (TEST P0-2-C/D)', () {
    test(
      'a full live page keeps hasMore; a short live page means no history',
      () {
        final m = merger();
        m.setLivePage(seq(8, 10).reversed.toList());
        expect(m.hasMore, isTrue);
        expect(m.merged().map((x) => x.id), ['m8', 'm9', 'm10']);

        final short = merger();
        short.setLivePage(seq(9, 10).reversed.toList());
        expect(short.hasMore, isFalse);
      },
    );

    test('older pages prepend without duplicates or gaps and stay ordered', () {
      final m = merger();
      m.setLivePage(seq(8, 10).reversed.toList());
      m.addOlderPage(seq(5, 7).reversed.toList());
      m.addOlderPage(seq(2, 4).reversed.toList());
      m.addOlderPage(seq(1, 1).reversed.toList());
      expect(m.hasMore, isFalse);
      expect(m.merged().map((x) => x.id), [
        for (var i = 1; i <= 10; i++) 'm$i',
      ]);
      expect(m.oldestLoaded?.id, 'm1');
    });

    test(
      'a message present in both the live page and an older page appears once',
      () {
        // The live window shifts when new messages arrive: m8 moves out of the
        // live page into "older" territory after m11 lands, but a previously
        // loaded older page may still hold it.
        final m = merger();
        m.setLivePage(seq(8, 10).reversed.toList());
        m.addOlderPage(seq(5, 7).reversed.toList());
        m.setLivePage(seq(9, 11).reversed.toList());
        m.addOlderPage([Msg('m8', 8000), Msg('m7', 7000), Msg('m6', 6000)]);
        final ids = m.merged().map((x) => x.id).toList();
        expect(ids, ['m5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11']);
        expect(ids.toSet().length, ids.length);
      },
    );

    test('live copies win over older copies of the same message (edits)', () {
      final m = merger();
      m.addOlderPage([
        Msg('p1', 1000, type: 'promise_request', promiseId: 'P'),
      ]);
      m.setLivePage([
        Msg('p1', 1000, type: 'promise_confirmed', promiseId: 'P'),
      ]);
      expect(m.merged().single.type, 'promise_confirmed');
    });

    test(
      'pending server timestamps sort last and ties break by id deterministically',
      () {
        final m = merger();
        m.setLivePage([Msg('local', null), Msg('b', 5000), Msg('a', 5000)]);
        expect(m.merged().map((x) => x.id), ['a', 'b', 'local']);
      },
    );

    test(
      'promise groups split by the page boundary are detected, supplements complete them',
      () {
        final m = merger();
        m.setLivePage([
          Msg('m20', 20000),
          Msg('p2c', 19000, type: 'promise_confirmed', promiseId: 'P2'),
          Msg('p1c', 18000, type: 'promise_confirmed', promiseId: 'P1'),
        ]);
        expect(m.missingPromiseRequestIds(), {'P1', 'P2'});
        m.addPromiseSupplement([
          Msg('p1r', 3000, type: 'promise_request', promiseId: 'P1'),
        ]);
        expect(m.missingPromiseRequestIds(), {'P2'});
        expect(m.supplementedPromiseIds(), {'P1'});
        expect(
          m.merged().first.id,
          'p1r',
          reason: 'supplement is ordered by time',
        );
        m.addOlderPage([
          Msg('p2r', 17000, type: 'promise_request', promiseId: 'P2'),
        ]);
        expect(m.missingPromiseRequestIds(), isEmpty);
      },
    );

    test(
      'the paging cursor ignores promise supplements (they are not part of the paged window)',
      () {
        final m = merger();
        m.setLivePage([
          Msg('m20', 20000),
          Msg('m19', 19000),
          Msg('p1c', 18000, type: 'promise_confirmed', promiseId: 'P1'),
        ]);
        // The request sits far below the window; everything between it and
        // p1c is still unloaded and must stay reachable by paging.
        m.addPromiseSupplement([
          Msg('p1r', 3000, type: 'promise_request', promiseId: 'P1'),
        ]);
        expect(m.merged().first.id, 'p1r');
        expect(m.oldestLoaded?.id, 'p1c');

        m.addOlderPage(seq(15, 17).reversed.toList());
        expect(m.oldestLoaded?.id, 'm15');
      },
    );

    test(
      'messages that slide out of the live window after paging stay visible',
      () {
        final m = merger();
        m.setLivePage(seq(8, 10).reversed.toList());
        m.addOlderPage(seq(5, 7).reversed.toList());
        // Two new messages arrive: the limit(3) listener now holds m10..m12
        // and no longer reports m8, m9.
        m.setLivePage(seq(10, 12).reversed.toList());
        expect(m.merged().map((x) => x.id), [
          for (var i = 5; i <= 12; i++) 'm$i',
        ]);
        expect(m.oldestLoaded?.id, 'm5');
      },
    );

    test(
      'a room that grows past one page during the session becomes pageable and keeps its first messages',
      () {
        final m = merger();
        m.setLivePage(seq(1, 2).reversed.toList());
        expect(m.hasMore, isFalse);
        m.setLivePage(seq(2, 4).reversed.toList());
        expect(m.merged().map((x) => x.id), ['m1', 'm2', 'm3', 'm4']);
        expect(m.hasMore, isTrue);
        // The cursor is the live window, so the next page re-covers anything
        // below it; duplicates are merged by id.
        expect(m.oldestLoaded?.id, 'm2');
        m.addOlderPage(seq(1, 1).reversed.toList());
        expect(m.hasMore, isFalse);
        expect(m.merged().map((x) => x.id), ['m1', 'm2', 'm3', 'm4']);
      },
    );

    test(
      'a partial first snapshot followed by a full one does not latch hasMore false',
      () {
        final m = merger();
        m.setLivePage([Msg('m10', 10000)]);
        expect(m.hasMore, isFalse);
        m.setLivePage(seq(8, 10).reversed.toList());
        expect(m.hasMore, isTrue);
      },
    );

    test(
      'when the live window jumps past everything loaded, stale pages are dropped instead of leaving a silent gap',
      () {
        final m = merger();
        m.setLivePage(seq(8, 10).reversed.toList());
        m.addOlderPage(seq(5, 7).reversed.toList());
        // Reconnect after a long gap: none of m8..m10 is in the new window.
        m.setLivePage(seq(30, 32).reversed.toList());
        expect(m.merged().map((x) => x.id), ['m30', 'm31', 'm32']);
        expect(m.hasMore, isTrue);
        expect(m.oldestLoaded?.id, 'm30');
      },
    );

    test('reset returns to an empty, pageable state', () {
      final m = merger();
      m.setLivePage(seq(1, 2).reversed.toList());
      m.reset();
      expect(m.merged(), isEmpty);
      expect(m.hasMore, isTrue);
      expect(m.loadedOlderPages, 0);
    });
  });
}
