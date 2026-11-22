/// Hands a `StreamBuilder` the same stream instance across rebuilds, and a new
/// one only when what the stream depends on changes.
///
/// `StreamBuilder(stream: service.watchX(uid))` builds a new stream on every
/// `build()`. `StreamBuilder` compares streams by identity, so each rebuild of
/// the surrounding widget cancelled the Firestore listener and opened another.
/// Moving the stream to `initState` fixes that but freezes it on the first
/// user id or argument; [of] keeps it tied to a [key] instead.
class KeyedStream<K, T> {
  K? _key;
  Stream<T>? _stream;

  /// Returns the stream created for [key], creating it only when [key] differs
  /// from the previous call's.
  Stream<T> of(K key, Stream<T> Function() create) {
    final current = _stream;
    if (current != null && _key == key) return current;
    _key = key;
    return _stream = create();
  }
}

/// The future counterpart of [KeyedStream], for a `FutureBuilder` whose future
/// is derived from a value that arrives in `build()`.
///
/// The source is compared by identity: a snapshot's data is the same object
/// until the next event, so one event starts one future however many times
/// the widget rebuilds.
class SourceFuture<S extends Object, T> {
  S? _source;
  Future<T>? _future;

  Future<T> of(S source, Future<T> Function() create) {
    final current = _future;
    if (current != null && identical(_source, source)) return current;
    _source = source;
    return _future = create();
  }
}
