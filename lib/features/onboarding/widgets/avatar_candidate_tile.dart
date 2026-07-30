import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'avatar_generation_models.dart';

/// 아바타 후보 단일 타일.
///
/// 정사각 비율, 라운드 코너, 선택 상태에서 deep plum 보더 + 우측 상단 체크 아이콘으로
/// 표시합니다. 색상에만 의존하지 않도록 체크 아이콘을 함께 제공합니다.
class AvatarCandidateTile extends StatelessWidget {
  final AvatarCandidate candidate;
  final bool isSelected;
  final int index;
  final VoidCallback onTap;

  const AvatarCandidateTile({
    super.key,
    required this.candidate,
    required this.isSelected,
    required this.index,
    required this.onTap,
  });

  static const Color _deepPlum = Color(0xFF4A2C40);
  static const Color _plumDeeper = Color(0xFF32172A);
  static const Color _surfaceContainer = Color(0xFFF4ECEE);

  @override
  Widget build(BuildContext context) {
    final previewBytes = candidate.previewBytes;
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(20),
      side: isSelected
          ? const BorderSide(color: _plumDeeper, width: 3)
          : BorderSide(color: Colors.black.withValues(alpha: 0.04), width: 1),
    );

    return Semantics(
      button: true,
      selected: isSelected,
      label: '아바타 후보 ${index + 1}${isSelected ? ', 선택됨' : ''}',
      child: Material(
        color: _surfaceContainer,
        shape: shape,
        clipBehavior: Clip.antiAlias,
        elevation: isSelected ? 6 : 0,
        shadowColor: _plumDeeper.withValues(alpha: 0.20),
        child: InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            onTap();
          },
          child: AspectRatio(
            aspectRatio: 1,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (previewBytes != null && previewBytes.isNotEmpty)
                  Image.memory(
                    previewBytes,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) =>
                        _brokenImage(),
                  )
                else
                  Image.network(
                    candidate.previewUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) =>
                        _brokenImage(),
                    loadingBuilder: (context, child, progress) {
                      if (progress == null) return child;
                      return Container(
                        color: _surfaceContainer,
                        alignment: Alignment.center,
                        child: const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: _deepPlum,
                          ),
                        ),
                      );
                    },
                  ),
                if (!isSelected)
                  Container(color: Colors.black.withValues(alpha: 0.04)),
                if (isSelected)
                  const Positioned(
                    top: 10,
                    right: 10,
                    child: _SelectionCheckBadge(),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _brokenImage() {
    return Container(
      color: _surfaceContainer,
      alignment: Alignment.center,
      child: const Icon(
        Icons.broken_image_outlined,
        color: Color(0xFF6B5A66),
        size: 28,
      ),
    );
  }
}

class _SelectionCheckBadge extends StatelessWidget {
  const _SelectionCheckBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 26,
      height: 26,
      decoration: const BoxDecoration(
        color: Color(0xFF32172A),
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Color(0x3332172A),
            blurRadius: 8,
            offset: Offset(0, 2),
          ),
        ],
      ),
      alignment: Alignment.center,
      child: const Icon(Icons.check_rounded, color: Colors.white, size: 18),
    );
  }
}
