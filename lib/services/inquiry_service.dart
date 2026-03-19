import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import 'storage_service.dart';

class InquiryService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final StorageService _storageService = StorageService();

  CollectionReference<Map<String, dynamic>> get _inquiriesRef =>
      _firestore.collection('app_inquiries');

  Future<void> submitInquiry({
    required String category,
    required String content,
    required bool allowContact,
    String sourceScreen = 'settings_inquiry',
  }) async {
    final inquirerId = await _storageService.getKakaoUserId();

    if (inquirerId == null || inquirerId.trim().isEmpty) {
      throw Exception('Kakao user id not found');
    }

    if (category.trim().isEmpty) {
      throw Exception('category is empty');
    }

    if (content.trim().isEmpty) {
      throw Exception('content is empty');
    }

    await _inquiriesRef.add({
      'inquirerId': inquirerId.trim(),
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
