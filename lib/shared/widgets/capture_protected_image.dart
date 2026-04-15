import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import 'profile_photo_blur.dart';

enum CaptureProtectedImageShape { roundedRect, circle }

class CaptureProtectedImage extends StatelessWidget {
  const CaptureProtectedImage({
    super.key,
    required this.imageUrl,
    this.fit = BoxFit.cover,
    this.borderRadius = 0,
    this.shape = CaptureProtectedImageShape.roundedRect,
    this.blurEnabled = false,
    this.blurSigma = 7,
    this.blurBadgeText,
    this.grayscale = false,
    this.iosSecureCaptureEnabled = true,
    this.backgroundColor = const Color(0xFFF3F4F6),
    this.placeholderIconColor = const Color(0xFF9CA3AF),
    this.placeholderIconSize = 28,
  });

  static const String _viewType =
      'com.yonsei.dating/capture_protected_image';

  final String imageUrl;
  final BoxFit fit;
  final double borderRadius;
  final CaptureProtectedImageShape shape;
  final bool blurEnabled;
  final double blurSigma;
  final String? blurBadgeText;
  final bool grayscale;
  final bool iosSecureCaptureEnabled;
  final Color backgroundColor;
  final Color placeholderIconColor;
  final double placeholderIconSize;

  bool get _usesNativeSecureImage =>
      !kIsWeb &&
      defaultTargetPlatform == TargetPlatform.iOS &&
      iosSecureCaptureEnabled;

  @override
  Widget build(BuildContext context) {
    if (_usesNativeSecureImage) {
      return _buildIosSecureImage();
    }
    return _buildFallbackImage();
  }

  Widget _buildIosSecureImage() {
    Widget child = UiKitView(
      viewType: _viewType,
      hitTestBehavior: PlatformViewHitTestBehavior.transparent,
      creationParams: {
        'imageUrl': imageUrl,
        'fit': fit == BoxFit.contain ? 'contain' : 'cover',
        'borderRadius': borderRadius,
        'isCircular': shape == CaptureProtectedImageShape.circle,
        'blurEnabled': blurEnabled,
        'blurSigma': blurSigma,
        'grayscale': grayscale,
        'backgroundColor': backgroundColor.toARGB32(),
        'placeholderIconColor': placeholderIconColor.toARGB32(),
        'placeholderIconSize': placeholderIconSize,
      },
      creationParamsCodec: const StandardMessageCodec(),
    );

    child = Stack(
      fit: StackFit.expand,
      children: [
        child,
        const Positioned.fill(child: _PlatformViewPointerShield()),
      ],
    );

    if (shape == CaptureProtectedImageShape.circle) {
      child = ClipOval(child: child);
    } else if (borderRadius > 0) {
      child = ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: child,
      );
    }

    if (!blurEnabled && (blurBadgeText == null || blurBadgeText!.trim().isEmpty)) {
      return child;
    }

    return Stack(
      fit: StackFit.expand,
      children: [
        child,
        if (blurEnabled)
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    CupertinoColors.black.withValues(alpha: 0.06),
                    CupertinoColors.black.withValues(alpha: 0.12),
                  ],
                ),
              ),
            ),
          ),
        if (blurBadgeText != null && blurBadgeText!.trim().isNotEmpty)
          Positioned(
            top: 14,
            right: 14,
            child: SafeArea(
              minimum: EdgeInsets.zero,
              child: Container(
                constraints: const BoxConstraints(maxWidth: 250),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: CupertinoColors.white.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: CupertinoColors.white.withValues(alpha: 0.98),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.14),
                      blurRadius: 14,
                      offset: const Offset(0, 5),
                    ),
                  ],
                ),
                child: Text(
                  blurBadgeText!,
                  textAlign: TextAlign.right,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF1E1A1C),
                    height: 1.2,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildFallbackImage() {
    Widget image = imageUrl.trim().isEmpty
        ? _buildPlaceholder()
        : Image.network(
            imageUrl,
            fit: fit,
            errorBuilder: (_, __, ___) => _buildPlaceholder(),
          );

    if (grayscale) {
      image = ColorFiltered(
        colorFilter: const ColorFilter.mode(
          CupertinoColors.systemGrey,
          BlendMode.saturation,
        ),
        child: image,
      );
    }

    if (blurEnabled) {
      image = ProfilePhotoBlur(
        enabled: true,
        sigma: blurSigma,
        badgeText: blurBadgeText,
        child: image,
      );
    }

    image = ColoredBox(color: backgroundColor, child: image);

    if (shape == CaptureProtectedImageShape.circle) {
      return ClipOval(child: image);
    }
    if (borderRadius > 0) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: image,
      );
    }
    return image;
  }

  Widget _buildPlaceholder() {
    return Center(
      child: Icon(
        CupertinoIcons.person_fill,
        size: placeholderIconSize,
        color: placeholderIconColor,
      ),
    );
  }
}

class _PlatformViewPointerShield extends StatelessWidget {
  const _PlatformViewPointerShield();

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: (_) {},
      onPointerMove: (_) {},
      onPointerUp: (_) {},
      onPointerCancel: (_) {},
      child: const SizedBox.expand(),
    );
  }
}
