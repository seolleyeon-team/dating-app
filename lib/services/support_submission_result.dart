class SupportSubmissionResult {
  final String caseId;
  final String? supportRoomId;

  const SupportSubmissionResult({required this.caseId, this.supportRoomId});

  bool get hasSupportChat =>
      supportRoomId != null && supportRoomId!.trim().isNotEmpty;
}
