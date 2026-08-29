/// Prevents a second tap on the same photo slot from starting another upload
/// while the first picker/upload flow is still running.
///
/// Slots remain independent so a user can upload different photos in parallel.
class AvatarUploadSubmissionGuard {
  final Set<int> _lockedSlots = <int>{};

  /// Marks [slotIndex] as in flight and returns whether this call acquired it.
  bool tryAcquire(int slotIndex) => _lockedSlots.add(slotIndex);

  /// Releases [slotIndex] after its upload flow finishes or is cancelled.
  void release(int slotIndex) {
    _lockedSlots.remove(slotIndex);
  }

  bool isLocked(int slotIndex) => _lockedSlots.contains(slotIndex);
}
