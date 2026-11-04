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
