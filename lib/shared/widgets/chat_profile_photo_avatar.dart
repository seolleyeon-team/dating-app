import 'package:flutter/cupertino.dart';

import '../../services/chat_profile_photo_service.dart';
import 'capture_protected_image.dart';

class ChatProfilePhotoAvatar extends StatefulWidget {
  const ChatProfilePhotoAvatar({
    super.key,
    required this.chatRoomId,
    required this.targetUid,
    required this.fallbackImageUrl,
    this.size = 48,
    this.grayscale = false,
    this.backgroundColor = const Color(0xFFF3F4F6),
    this.placeholderIconColor = const Color(0xFF9CA3AF),
    this.placeholderIconSize = 24,
    this.service,
  });

  final String chatRoomId;
  final String targetUid;
  final String fallbackImageUrl;
  final double size;
  final bool grayscale;
  final Color backgroundColor;
  final Color placeholderIconColor;
  final double placeholderIconSize;
  final ChatProfilePhotoService? service;

  @override
  State<ChatProfilePhotoAvatar> createState() => _ChatProfilePhotoAvatarState();
}

class _ChatProfilePhotoAvatarState extends State<ChatProfilePhotoAvatar> {
  late final ChatProfilePhotoService _service =
      widget.service ?? ChatProfilePhotoService();
  late Future<ChatProfilePhotoResult> _photoFuture = _load();

  @override
  void didUpdateWidget(covariant ChatProfilePhotoAvatar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.chatRoomId != widget.chatRoomId ||
        oldWidget.targetUid != widget.targetUid ||
        oldWidget.fallbackImageUrl != widget.fallbackImageUrl) {
      _photoFuture = _load();
    }
  }

  Future<ChatProfilePhotoResult> _load() {
    return _service.getChatProfilePhoto(
      chatRoomId: widget.chatRoomId,
      targetUid: widget.targetUid,
      fallbackAvatarUrl: widget.fallbackImageUrl,
    );
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: FutureBuilder<ChatProfilePhotoResult>(
        future: _photoFuture,
        builder: (context, snapshot) {
          final result = snapshot.data;
          final imageUrl = result?.imageUrl.isNotEmpty == true
              ? result!.imageUrl
              : widget.fallbackImageUrl;
          return CaptureProtectedImage(
            imageUrl: imageUrl,
            shape: CaptureProtectedImageShape.circle,
            fit: BoxFit.cover,
            grayscale: widget.grayscale,
            backgroundColor: widget.backgroundColor,
            placeholderIconColor: widget.placeholderIconColor,
            placeholderIconSize: widget.placeholderIconSize,
          );
        },
      ),
    );
  }
}
