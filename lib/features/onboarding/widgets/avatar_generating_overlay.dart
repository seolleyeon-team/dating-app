import 'dart:ui';

import 'package:flutter/material.dart';

/// 아바타 생성 중 표시되는 전체화면 오버레이.
///
/// 사진 업로드 화면 위에 BackdropFilter 블러 + 반투명 카드 형태로 표시되며
/// 배경 인터랙션을 차단합니다. dismiss는 허용하지 않습니다.
///
/// 색상 톤: 따뜻한 아이보리(`#F9F9F7`) 카드 + deep plum 텍스트/스피너 (`#32172A` / `#4A2C40`).
class AvatarGeneratingOverlay extends StatelessWidget {
  final bool visible;

  const AvatarGeneratingOverlay({super.key, this.visible = true});

  static const Color _deepPlum = Color(0xFF32172A);
  static const Color _plumSoft = Color(0xFF4A2C40);
  static const Color _textPrimary = Color(0xFF2D1B27);
  static const Color _textSecondary = Color(0xFF6B5A66);
  static const Color _warmOffWhite = Color(0xFFF9F9F7);
  static const Color _surfaceContainer = Color(0xFFF4ECEE);

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      transitionBuilder: (child, animation) =>
          FadeTransition(opacity: animation, child: child),
      child: visible
          ? Stack(
              key: const ValueKey('avatar_generating_overlay_visible'),
              children: [
                Positioned.fill(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                    child: Container(color: _deepPlum.withValues(alpha: 0.20)),
                  ),
                ),
                ModalBarrier(
                  color: Colors.transparent,
                  dismissible: false,
                ),
                const Center(child: _GeneratingCard()),
              ],
            )
          : const SizedBox.shrink(
              key: ValueKey('avatar_generating_overlay_hidden'),
            ),
    );
  }
}

class _GeneratingCard extends StatelessWidget {
  const _GeneratingCard();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 28),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 28,
                vertical: 32,
              ),
              decoration: BoxDecoration(
                color: AvatarGeneratingOverlay._warmOffWhite.withValues(
                  alpha: 0.95,
                ),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                  color: AvatarGeneratingOverlay._surfaceContainer,
                  width: 1,
                ),
                boxShadow: [
                  BoxShadow(
                    color: AvatarGeneratingOverlay._plumSoft.withValues(
                      alpha: 0.12,
                    ),
                    blurRadius: 32,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: const Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 56,
                    height: 56,
                    child: CircularProgressIndicator(
                      strokeWidth: 4,
                      color: AvatarGeneratingOverlay._deepPlum,
                      backgroundColor: AvatarGeneratingOverlay._surfaceContainer,
                    ),
                  ),
                  SizedBox(height: 22),
                  Text(
                    '아바타 생성중...',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: AvatarGeneratingOverlay._deepPlum,
                      height: 1.2,
                      letterSpacing: -0.2,
                    ),
                  ),
                  SizedBox(height: 12),
                  Text(
                    '프로필에는 실제 사진이 아닌\n아바타가 표시돼요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: AvatarGeneratingOverlay._textPrimary,
                      height: 1.5,
                    ),
                  ),
                  SizedBox(height: 14),
                  Text(
                    '잠시만 기다려주세요.\n안전한 프로필 이미지를 만들고 있어요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 13,
                      color: AvatarGeneratingOverlay._textSecondary,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
