import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import 'firebase_runtime.dart';
import 'support_submission_result.dart';

class IssueReportService {
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: firebaseFunctionsRegion,
  );

  Future<SupportSubmissionResult> submitIssueReport({
    required String category,
    required String content,
    required bool allowOperationsFollowUp,
    String sourceScreen = 'settings_issue_report',
  }) async {
    if (FirebaseAuth.instance.currentUser?.uid.trim().isEmpty != false) {
      throw StateError('Firebase session is not ready');
    }

    if (category.trim().isEmpty) {
      throw Exception('category is empty');
    }

    if (content.trim().isEmpty) {
      throw Exception('content is empty');
    }

    final result = await _functions
        .httpsCallable('submitIssueReport')
        .call<dynamic>({
          'category': category.trim(),
          'content': content.trim(),
          'allowOperationsFollowUp': allowOperationsFollowUp,
          'sourceScreen': sourceScreen,
          'platform': defaultTargetPlatform.name,
        });
    final data = Map<String, dynamic>.from(result.data as Map? ?? const {});
    return SupportSubmissionResult(
      caseId: data['caseId']?.toString() ?? '',
      supportRoomId: data['supportRoomId']?.toString(),
    );
  }
}
