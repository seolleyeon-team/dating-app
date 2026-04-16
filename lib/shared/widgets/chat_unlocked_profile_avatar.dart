import 'package:flutter/cupertino.dart';

import '../constants/photo_blur_constants.dart';
import '../../features/matching/services/profile_photo_access_service.dart';
import 'capture_protected_image.dart';

class ChatUnlockedProfileAvatar extends StatefulWidget {
  const ChatUnlockedProfileAvatar({
    super.key,
    required this.currentUserId,
    required this.targetUserId,
    required this.imageUrl,
    this.size = 48,
    this.borderWidth = 0,
    this.borderColor,
    this.backgroundColor = const Color(0xFFF3F4F6),
    this.placeholderIconColor = const Color(0xFF9CA3AF),
    this.placeholderIconSize = 24,
  });

  final String currentUserId;
  final String targetUserId;
  final String imageUrl;
  final double size;
  final double borderWidth;
  final Color? borderColor;
  final Color backgroundColor;
  final Color placeholderIconColor;
  final double placeholderIconSize;

  @override
  State<ChatUnlockedProfileAvatar> createState() =>
      _ChatUnlockedProfileAvatarState();
}

class _ChatUnlockedProfileAvatarState extends State<ChatUnlockedProfileAvatar> {
  static final ProfilePhotoAccessService _photoAccessService =
      ProfilePhotoAccessService();

  late Future<bool> _unlockFuture;

  @override
  void initState() {
    super.initState();
    _unlockFuture = _loadUnlockState();
  }

  @override
  void didUpdateWidget(covariant ChatUnlockedProfileAvatar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentUserId != widget.currentUserId ||
        oldWidget.targetUserId != widget.targetUserId) {
      _unlockFuture = _loadUnlockState();
    }
  }

  Future<bool> _loadUnlockState() {
    return _photoAccessService.canViewUnblurredProfilePhotos(
      viewerUserId: widget.currentUserId,
      targetUserId: widget.targetUserId,
    );
  }

  @override
  Widget build(BuildContext context) {
    final avatar = FutureBuilder<bool>(
      future: _unlockFuture,
      builder: (context, snapshot) {
        final isUnlocked = snapshot.data == true;
        return CaptureProtectedImage(
          imageUrl: widget.imageUrl,
          fit: BoxFit.cover,
          shape: CaptureProtectedImageShape.circle,
          blurEnabled: !isUnlocked,
          blurSigma: kLockedProfilePhotoBlurSigma,
          backgroundColor: widget.backgroundColor,
          placeholderIconColor: widget.placeholderIconColor,
          placeholderIconSize: widget.placeholderIconSize,
        );
      },
    );

    return Container(
      width: widget.size,
      height: widget.size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: widget.backgroundColor,
        border: widget.borderWidth > 0
            ? Border.all(
                color: widget.borderColor ?? CupertinoColors.systemGrey4,
                width: widget.borderWidth,
              )
            : null,
      ),
      clipBehavior: Clip.antiAlias,
      child: avatar,
    );
  }
}
