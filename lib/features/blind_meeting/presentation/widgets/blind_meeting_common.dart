// =============================================================================
// 3:3 블라인드 취향 미팅 — 공통 위젯
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_common.dart
//
// 카드 / CTA / pill 스타일은 이벤트 탭(3:3 시즌 미팅)에서 쓰는 값과 동일하게
// 맞춘다. 형태 값은 blind_meeting_palette.dart의 kEvent* 상수를 쓴다.
// =============================================================================

import 'package:flutter/material.dart';

import '../theme/blind_meeting_palette.dart';

/// 차분한 상단 바.
class BlindMeetingAppBar extends StatelessWidget {
  final String title;
  final VoidCallback? onBack;
  final Widget? trailing;

  const BlindMeetingAppBar({
    super.key,
    required this.title,
    this.onBack,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          children: [
            SizedBox(
              width: 48,
              height: 48,
              child: onBack == null
                  ? null
                  : IconButton(
                      onPressed: onBack,
                      icon: Icon(Icons.arrow_back_ios_new, size: 20),
                      color: palette.ink,
                      tooltip: '뒤로',
                    ),
            ),
            Expanded(
              child: Text(
                title,
                textAlign: TextAlign.center,
                style: BlindMeetingText.sectionTitle(palette.ink),
              ),
            ),
            SizedBox(width: 48, height: 48, child: trailing),
          ],
        ),
      ),
    );
  }
}

/// 부드러운 카드 — 시즌 미팅 카드와 같은 radius / 핑크 기운 섀도를 쓴다.
class BlindMeetingCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? background;
  final bool highlighted;

  /// 카드 radius. 히어로급 카드는 [kEventHeroRadius]를 넘긴다.
  final double radius;

  /// 외곽선 표시 여부. 시즌 미팅 히어로 카드는 선 없이 섀도만 쓴다.
  final bool bordered;

  const BlindMeetingCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.background,
    this.highlighted = false,
    this.radius = kEventCardRadius,
    this.bordered = true,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: background ?? palette.surface,
        borderRadius: BorderRadius.circular(radius),
        border: bordered || highlighted
            ? Border.all(
                color: highlighted
                    ? palette.accent.withValues(alpha: 0.35)
                    : palette.border.withValues(alpha: 0.6),
              )
            : null,
        boxShadow: [
          BoxShadow(
            color: palette.overlay,
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}

/// 기본 CTA 버튼 — 시즌 미팅 '팀 만들고 시작하기' 버튼과 같은 시스템.
class BlindMeetingPrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;

  const BlindMeetingPrimaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.loading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final enabled = onPressed != null && !loading;
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(kEventCtaHeight / 2),
          boxShadow: enabled
              ? [
                  BoxShadow(
                    color: palette.accent.withValues(alpha: 0.35),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ]
              : const [],
        ),
        child: SizedBox(
          width: double.infinity,
          height: kEventCtaHeight,
          child: FilledButton(
            onPressed: enabled ? onPressed : null,
            style: FilledButton.styleFrom(
              backgroundColor: palette.accent,
              foregroundColor: Colors.white,
              // 비활성: 핑크 톤은 유지하되 라벨을 흰색으로 두면 읽히지 않는다.
              // 연한 로즈 배경 위에서 대비가 나오는 짙은 로즈를 쓴다.
              disabledBackgroundColor: palette.accent.withValues(alpha: 0.28),
              disabledForegroundColor: palette.attention,
              elevation: 0,
              shadowColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(kEventCtaHeight / 2),
              ),
              textStyle: const TextStyle(
                fontFamily: BlindMeetingText.fontFamily,
                fontSize: 17,
                fontWeight: FontWeight.w700,
              ),
            ),
            child: loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      if (icon != null) ...[
                        Icon(icon, size: 20),
                        const SizedBox(width: 8),
                      ],
                      Flexible(
                        child: Text(
                          label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

/// 보조 버튼.
class BlindMeetingSecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;

  const BlindMeetingSecondaryButton({
    super.key,
    required this.label,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: palette.accent,
          backgroundColor: palette.surface,
          side: BorderSide(color: palette.accent.withValues(alpha: 0.35)),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(26),
          ),
          textStyle: const TextStyle(
            fontFamily: BlindMeetingText.fontFamily,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
        child: Text(label),
      ),
    );
  }
}

/// 단일/복수 선택 옵션 타일.
class BlindMeetingOptionTile extends StatelessWidget {
  final String label;
  final String? description;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  const BlindMeetingOptionTile({
    super.key,
    required this.label,
    this.description,
    required this.selected,
    this.enabled = true,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final foreground = enabled ? palette.ink : palette.inkFaint;

    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      label: label,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Material(
          color: selected ? palette.surfaceMuted : palette.surface,
          borderRadius: BorderRadius.circular(kEventCardRadius),
          child: InkWell(
            borderRadius: BorderRadius.circular(kEventCardRadius),
            onTap: enabled ? onTap : null,
            child: Container(
              constraints: const BoxConstraints(minHeight: 56),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(kEventCardRadius),
                border: Border.all(
                  color: selected
                      ? palette.accent
                      : palette.border.withValues(alpha: 0.6),
                  width: selected ? 1.6 : 1,
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(label, style: BlindMeetingText.body(foreground)),
                        if (description != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            description!,
                            style: BlindMeetingText.caption(palette.inkFaint),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Icon(
                    selected
                        ? Icons.radio_button_checked
                        : Icons.radio_button_unchecked,
                    size: 20,
                    color: selected ? palette.accent : palette.inkFaint,
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

/// 단계 진행 표시 (1/4 형태 + 진행 바).
class BlindMeetingStepProgress extends StatelessWidget {
  final int step;
  final int totalSteps;

  const BlindMeetingStepProgress({
    super.key,
    required this.step,
    required this.totalSteps,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final ratio = totalSteps <= 0 ? 0.0 : (step / totalSteps).clamp(0.0, 1.0);

    return Semantics(
      label: '$totalSteps단계 중 $step단계',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$step/$totalSteps',
            style: BlindMeetingText.label(palette.accent),
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: 4,
              backgroundColor: palette.surfaceMuted,
              valueColor: AlwaysStoppedAnimation<Color>(palette.accent),
            ),
          ),
        ],
      ),
    );
  }
}

/// 정보/안내 pill — 시즌 미팅 'SAFE MATCHING' 배지와 같은 계열.
class BlindMeetingBadge extends StatelessWidget {
  final String label;
  final IconData? icon;
  final Color? color;

  const BlindMeetingBadge({
    super.key,
    required this.label,
    this.icon,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final tint = color ?? palette.accent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: tint.withValues(alpha: 0.12)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: tint),
            const SizedBox(width: 4),
          ],
          Text(label, style: BlindMeetingText.label(tint)),
        ],
      ),
    );
  }
}

/// 오류 + 재시도 상태.
class BlindMeetingErrorState extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;

  const BlindMeetingErrorState({
    super.key,
    required this.message,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return BlindMeetingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('잠시 문제가 생겼어요', style: BlindMeetingText.title(palette.ink)),
          const SizedBox(height: 8),
          Text(message, style: BlindMeetingText.body(palette.inkSoft)),
          if (onRetry != null) ...[
            const SizedBox(height: 16),
            BlindMeetingSecondaryButton(label: '다시 시도', onPressed: onRetry),
          ],
        ],
      ),
    );
  }
}

/// 비어 있는 상태.
class BlindMeetingEmptyState extends StatelessWidget {
  final String title;
  final String description;

  const BlindMeetingEmptyState({
    super.key,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return BlindMeetingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: BlindMeetingText.sectionTitle(palette.ink)),
          const SizedBox(height: 8),
          Text(description, style: BlindMeetingText.body(palette.inkSoft)),
        ],
      ),
    );
  }
}

/// 시즌 미팅 하단 구분선과 같은 그라데이션 hairline.
class BlindMeetingSectionDivider extends StatelessWidget {
  const BlindMeetingSectionDivider({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return Container(
      height: 1,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Colors.transparent, palette.border, Colors.transparent],
        ),
      ),
    );
  }
}
