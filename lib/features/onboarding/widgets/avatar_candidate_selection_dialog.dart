import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'avatar_candidate_tile.dart';
import 'avatar_generation_models.dart';

/// 아바타 후보 4장(또는 그 이하)을 보여주는 선택 모달.
///
/// - 배경은 [BackdropFilter]로 흐려진 상태.
/// - 카드는 따뜻한 아이보리 / deep plum 톤.
/// - 2x2 그리드, 선택된 후보는 deep plum 보더 + 우측 상단 체크 아이콘.
/// - 하단 CTA "이 사진으로 할게요!"는 후보가 선택되기 전까지 비활성.
/// - 승인 중에는 텍스트가 "저장하는 중..."으로 바뀌고 비활성 처리.
///
/// 다이얼로그는 사용자의 명시적 확정/뒤로가기 외에는 dismiss되지 않습니다.
class AvatarCandidateSelectionDialog extends StatefulWidget {
  final List<AvatarCandidate> candidates;
  final bool isApproving;
  final String? errorMessage;
  final Future<void> Function(AvatarCandidate selected) onConfirm;
  final VoidCallback? onCancel;

  const AvatarCandidateSelectionDialog({
    super.key,
    required this.candidates,
    required this.onConfirm,
    this.isApproving = false,
    this.errorMessage,
    this.onCancel,
  });

  @override
  State<AvatarCandidateSelectionDialog> createState() =>
      _AvatarCandidateSelectionDialogState();
}

class _AvatarCandidateSelectionDialogState
    extends State<AvatarCandidateSelectionDialog> {
  static const Color _deepPlum = Color(0xFF32172A);
  static const Color _plumSoft = Color(0xFF4A2C40);
  static const Color _warmOffWhite = Color(0xFFF9F9F7);
  static const Color _surfaceContainer = Color(0xFFF4ECEE);
  static const Color _textPrimary = Color(0xFF2D1B27);
  static const Color _textSecondary = Color(0xFF6B5A66);

  String? _selectedCandidateId;

  @override
  Widget build(BuildContext context) {
    final candidates = widget.candidates;
    final canConfirm =
        _selectedCandidateId != null &&
        candidates.isNotEmpty &&
        !widget.isApproving;
    final selected = _resolveSelected();

    final mediaQuery = MediaQuery.of(context);
    final maxModalHeight = mediaQuery.size.height * 0.88;

    return Stack(
      children: [
        Positioned.fill(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
            child: Container(color: _deepPlum.withValues(alpha: 0.30)),
          ),
        ),
        const ModalBarrier(color: Colors.transparent, dismissible: false),
        SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxHeight: maxModalHeight),
                child: Material(
                  color: _warmOffWhite,
                  borderRadius: BorderRadius.circular(36),
                  elevation: 0,
                  child: Container(
                    decoration: BoxDecoration(
                      color: _warmOffWhite,
                      borderRadius: BorderRadius.circular(36),
                      border: Border.all(color: _surfaceContainer, width: 1),
                      boxShadow: [
                        BoxShadow(
                          color: _plumSoft.withValues(alpha: 0.12),
                          blurRadius: 40,
                          offset: const Offset(0, 12),
                        ),
                      ],
                    ),
                    padding: const EdgeInsets.fromLTRB(28, 32, 28, 28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const _DialogHeader(),
                        const SizedBox(height: 20),
                        if (candidates.isEmpty)
                          const _EmptyCandidates()
                        else
                          _CandidateGrid(
                            candidates: candidates,
                            selectedCandidateId: _selectedCandidateId,
                            onSelected: widget.isApproving
                                ? null
                                : _handleCandidateTap,
                          ),
                        if (widget.errorMessage != null) ...[
                          const SizedBox(height: 16),
                          _ErrorBanner(message: widget.errorMessage!),
                        ],
                        const SizedBox(height: 24),
                        _ConfirmButton(
                          enabled: canConfirm,
                          isApproving: widget.isApproving,
                          onPressed: canConfirm && selected != null
                              ? () => widget.onConfirm(selected)
                              : null,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  AvatarCandidate? _resolveSelected() {
    final id = _selectedCandidateId;
    if (id == null) return null;
    for (final c in widget.candidates) {
      if (c.candidateId == id) return c;
    }
    return null;
  }

  void _handleCandidateTap(AvatarCandidate candidate) {
    setState(() {
      _selectedCandidateId = candidate.candidateId;
    });
  }
}

class _DialogHeader extends StatelessWidget {
  const _DialogHeader();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '프로필에 지정할\n아바타를 선택해주세요',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 22,
            fontWeight: FontWeight.w700,
            color: _AvatarCandidateSelectionDialogState._deepPlum,
            height: 1.3,
            letterSpacing: -0.3,
          ),
        ),
        SizedBox(height: 10),
        Text(
          '선택한 아바타만 프로필에 표시돼요.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 13.5,
            color: _AvatarCandidateSelectionDialogState._textSecondary,
            height: 1.5,
          ),
        ),
        SizedBox(height: 4),
        Text(
          '원본 사진은 상대방에게 공개되지 않아요.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 12,
            color: _AvatarCandidateSelectionDialogState._textSecondary,
            height: 1.5,
          ),
        ),
      ],
    );
  }
}

class _CandidateGrid extends StatelessWidget {
  final List<AvatarCandidate> candidates;
  final String? selectedCandidateId;
  final ValueChanged<AvatarCandidate>? onSelected;

  const _CandidateGrid({
    required this.candidates,
    required this.selectedCandidateId,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 1,
      ),
      itemCount: candidates.length,
      itemBuilder: (context, index) {
        final candidate = candidates[index];
        return AvatarCandidateTile(
          candidate: candidate,
          isSelected: candidate.candidateId == selectedCandidateId,
          index: index,
          onTap: () => onSelected?.call(candidate),
        );
      },
    );
  }
}

class _EmptyCandidates extends StatelessWidget {
  const _EmptyCandidates();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      decoration: BoxDecoration(
        color: _AvatarCandidateSelectionDialogState._surfaceContainer,
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Text(
        '안전한 아바타 후보를 만들지 못했어요.\n다른 사진으로 다시 시도해주세요.',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 13,
          color: _AvatarCandidateSelectionDialogState._textPrimary,
          height: 1.5,
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFDAD6),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 12.5,
          color: Color(0xFF93000A),
          height: 1.4,
        ),
      ),
    );
  }
}

class _ConfirmButton extends StatelessWidget {
  final bool enabled;
  final bool isApproving;
  final VoidCallback? onPressed;

  const _ConfirmButton({
    required this.enabled,
    required this.isApproving,
    required this.onPressed,
  });

  static const Color _plumSoft = _AvatarCandidateSelectionDialogState._plumSoft;
  static const Color _deepPlum = _AvatarCandidateSelectionDialogState._deepPlum;
  static const Color _surfaceContainer =
      _AvatarCandidateSelectionDialogState._surfaceContainer;
  static const Color _textSecondary =
      _AvatarCandidateSelectionDialogState._textSecondary;

  @override
  Widget build(BuildContext context) {
    final disabled = !enabled || isApproving || onPressed == null;
    final label = isApproving ? '저장하는 중...' : '이 사진으로 할게요!';

    return SizedBox(
      width: double.infinity,
      child: Semantics(
        button: true,
        enabled: !disabled,
        label: '이 사진으로 할게요',
        child: ElevatedButton(
          onPressed: disabled
              ? null
              : () {
                  HapticFeedback.mediumImpact();
                  onPressed!();
                },
          style: ElevatedButton.styleFrom(
            backgroundColor: _deepPlum,
            disabledBackgroundColor: _surfaceContainer,
            foregroundColor: Colors.white,
            disabledForegroundColor: _textSecondary,
            elevation: disabled ? 0 : 8,
            shadowColor: _plumSoft.withValues(alpha: 0.25),
            shape: const StadiumBorder(),
            padding: const EdgeInsets.symmetric(vertical: 18),
            textStyle: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 15,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (isApproving) ...[
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(width: 10),
              ],
              Text(label),
            ],
          ),
        ),
      ),
    );
  }
}
