/// Bookkeeping for a live list that listens to "the newest N" documents and
/// raises N when the user reaches the end of what is loaded.
///
/// A snapshot listener has no cursor to continue from, so a paged live list
/// widens its window instead of appending pages. The window only grows when
/// the previous one came back full: a short result means there is nothing
/// older to ask for.
class GrowingQueryWindow {
  GrowingQueryWindow({required this.pageSize})
    : assert(pageSize > 0),
      _limit = pageSize;

  final int pageSize;
  int _limit;

  /// The `limit` the current listener should use.
  int get limit => _limit;

  /// Whether the last snapshot filled the window, so older items may exist.
  bool mayHaveMore(int loadedCount) => loadedCount >= _limit;

  /// Widens the window when the list is scrolled to within [threshold] pixels
  /// of its end and the window is full. Returns whether the limit changed, in
  /// which case the caller replaces its listener.
  ///
  /// Until the wider snapshot arrives [loadedCount] is below the new limit,
  /// so repeated scroll notifications cannot widen it twice.
  bool growIfNeeded({
    required int loadedCount,
    required double extentAfter,
    double threshold = 240,
  }) {
    if (extentAfter > threshold || !mayHaveMore(loadedCount)) return false;
    _limit += pageSize;
    return true;
  }
}
