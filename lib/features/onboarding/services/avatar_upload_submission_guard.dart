/// Prevents a second tap on the same photo slot from starting another upload
/// while the first picker/upload flow is still running.
///
/// Slots remain independent so a user can upload different photos in parallel.
class AvatarUploadSubmissionGuard {
  final Set<int> _activeSlots = <int>{};

  /// Marks [slotIndex] as active and returns whether this call acquired it.
  bool tryAcquire(int slotIndex) => _activeSlots.add(slotIndex);

  /// Releases [slotIndex] after its upload flow finishes or is cancelled.
  void release(int slotIndex) {
    _activeSlots.remove(slotIndex);
  }

  bool isActive(int slotIndex) => _activeSlots.contains(slotIndex);
}
