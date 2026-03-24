import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import 'storage_service.dart';

class IssueReportService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final StorageService _storageService = StorageService();

  CollectionReference<Map<String, dynamic>> get _reportsRef =>
      _firestore.collection('app_issue_reports');

  Future<void> submitIssueReport({
    required String category,
    required String content,
    required bool allowContact,
    String sourceScreen = 'settings_issue_report',
  }) async {
    final reporterId = await _storageService.getKakaoUserId();

    if (reporterId == null || reporterId.trim().isEmpty) {
      throw Exception('Kakao user id not found');
    }

    if (category.trim().isEmpty) {
      throw Exception('category is empty');
    }

    if (content.trim().isEmpty) {
      throw Exception('content is empty');
    }

    await _reportsRef.add({
      'reporterId': reporterId,
      'category': category.trim(),
      'content': content.trim(),
      'allowContact': allowContact,
      'sourceScreen': sourceScreen,
      'platform': defaultTargetPlatform.name,
      'status': 'pending',
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }
}
