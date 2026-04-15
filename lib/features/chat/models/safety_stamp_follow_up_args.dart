class SafetyStampFollowUpArgs {
  final String roomId;
  final String promiseId;
  final String? notificationId;

  const SafetyStampFollowUpArgs({
    required this.roomId,
    required this.promiseId,
    this.notificationId,
  });
}
