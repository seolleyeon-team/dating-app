/// Prevents duplicate image-picker submissions while a slot is awaiting a
/// picker result or a backend upload response.
class AvatarUploadSubmissionGuard {
  final Set<int> _lockedSlots = <int>{};

  bool tryAcquire(int slotIndex) {
    return _lockedSlots.add(slotIndex);
  }

  void release(int slotIndex) {
    _lockedSlots.remove(slotIndex);
  }

  bool isLocked(int slotIndex) => _lockedSlots.contains(slotIndex);
}
