/// P0-2: bounded message history.
///
/// The room screen keeps ONE realtime listener on the newest page
/// (`orderBy createdAt desc, limit pageSize`) and loads older history with
/// one-shot cursor queries (`startAfterDocument`). This merger turns those
/// two sources into the ascending list the UI renders, with no duplicates,
/// no gaps and deterministic ordering:
///
///   - a message id appears once even if it is in the live page and an older
///     page (the live page shifts as new messages arrive)
///   - ordering is by `createdAt` then id, exactly the query order
///   - `hasMore` is derived from the size of the last loaded page
///
/// Promise cards: the UI merges `promise_*` messages by `promiseId`. If a
/// lifecycle message is loaded but its `promise_request` sits beyond the
/// loaded window, [missingPromiseRequestIds] names the promise so the caller
/// can fetch that bounded group (`where promiseId ==`) instead of the whole
/// history.
class MessagePageMerger<T> {
  MessagePageMerger({
    required this.pageSize,
    required this.idOf,
    required this.createdAtMillisOf,
    required this.typeOf,
    required this.promiseIdOf,
  });

  final int pageSize;
  final String Function(T) idOf;

  /// null when `createdAt` is a pending server timestamp (local write); such
  /// messages sort last (newest), which is what the user expects to see.
  final int? Function(T) createdAtMillisOf;
  final String Function(T) typeOf;
  final String? Function(T) promiseIdOf;

  List<T> _livePage = const [];
  final List<List<T>> _olderPages = [];
  final Map<String, T> _promiseSupplements = {};
  bool _hasMore = true;

  bool get hasMore => _hasMore;
  int get loadedOlderPages => _olderPages.length;

  /// Replaces the realtime newest page (descending order as queried).
  void setLivePage(List<T> newestFirst) {
    _livePage = List<T>.unmodifiable(newestFirst);
    // With fewer than a full page in the live window there is nothing older.
    if (_olderPages.isEmpty && newestFirst.length < pageSize) _hasMore = false;
  }

  /// Appends one older page (descending order as queried).
  void addOlderPage(List<T> newestFirst) {
    _olderPages.add(List<T>.unmodifiable(newestFirst));
    if (newestFirst.length < pageSize) _hasMore = false;
  }

  /// Adds messages fetched to complete a promise group.
  void addPromiseSupplement(List<T> messages) {
    for (final message in messages) {
      _promiseSupplements[idOf(message)] = message;
    }
  }

  /// The oldest loaded message (cursor for the next older page), or null.
  T? get oldestLoaded {
    final all = merged();
    return all.isEmpty ? null : all.first;
  }

  /// Ascending, de-duplicated, deterministically ordered.
  List<T> merged() {
    final byId = <String, T>{};
    // Older pages first, then the live page, so the live (fresher) copy of a
    // message wins when both hold it.
    for (final page in _olderPages) {
      for (final message in page) {
        byId[idOf(message)] = message;
      }
    }
    for (final message in _promiseSupplements.values) {
      byId.putIfAbsent(idOf(message), () => message);
    }
    for (final message in _livePage) {
      byId[idOf(message)] = message;
    }
    final list = byId.values.toList();
    list.sort(_compareAscending);
    return list;
  }

  int _compareAscending(T a, T b) {
    final ta = createdAtMillisOf(a);
    final tb = createdAtMillisOf(b);
    if (ta == null && tb == null) return idOf(a).compareTo(idOf(b));
    if (ta == null) return 1;
    if (tb == null) return -1;
    final byTime = ta.compareTo(tb);
    if (byTime != 0) return byTime;
    return idOf(a).compareTo(idOf(b));
  }

  /// Promise ids whose `promise_request` message is not loaded although a
  /// later lifecycle message of the same promise is.
  Set<String> missingPromiseRequestIds() {
    final seenRequest = <String>{};
    final referenced = <String>{};
    for (final message in merged()) {
      final type = typeOf(message);
      if (!type.startsWith('promise_')) continue;
      final promiseId = promiseIdOf(message);
      if (promiseId == null || promiseId.isEmpty) continue;
      referenced.add(promiseId);
      if (type == 'promise_request') seenRequest.add(promiseId);
    }
    return referenced.difference(seenRequest);
  }

  /// Ids of promise groups already supplemented (never refetch them).
  Set<String> supplementedPromiseIds() {
    return {
      for (final message in _promiseSupplements.values)
        if (promiseIdOf(message) != null) promiseIdOf(message)!,
    };
  }

  void reset() {
    _livePage = const [];
    _olderPages.clear();
    _promiseSupplements.clear();
    _hasMore = true;
  }
}
