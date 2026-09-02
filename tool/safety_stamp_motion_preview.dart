import 'package:flutter/material.dart';
import 'package:seolleyeon/features/chat/screens/safety_stamp_screen.dart';

void main() {
  runApp(
    const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: SafetyStampScreen(
        roomId: '',
        promiseId: '',
        currentUserId: 'preview-me',
        partnerId: 'preview-partner',
        partnerName: '상대방',
        myName: '나',
        motionPreviewMode: true,
      ),
    ),
  );
}
