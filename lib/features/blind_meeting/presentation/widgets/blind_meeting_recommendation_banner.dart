// =============================================================================
// 3:3 블라인드 취향 미팅 — 추천 안내 fade 배너
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_recommendation_banner.dart
//
// 매칭 완료 직후 약 3초간 fade in/out 으로 노출하고 자연스럽게 사라진다.
//  - modal이 아니므로 사용자의 다음 동작을 막지 않는다
//  - 접근성 설정에서 모션 감소가 켜져 있으면 애니메이션 없이 표시
//  - screen reader announcement 지원
//  - `최적의 상대를 추천했어요` 같은 검증되지 않은 과장 표현을 쓰지 않는다
// =============================================================================

import 'package:flutter/material.dart';

import '../theme/blind_meeting_palette.dart';

/// 일반 미팅 안내 문구.
const String blindMeetingRecommendationMessage =
    '관심사, 미팅 목적, 대화 분위기와 음주 성향을 반영해\n잘 맞을 가능성이 높은 여섯 명을 구성했어요.';

/// 무알코올 미팅 안내 문구.
const String blindMeetingAlcoholFreeRecommendationMessage =
    '여섯 명 모두 비음주 조건을 선택했어요.\n관심사와 대화 분위기를 반영해 팀을 구성했어요.';

class BlindMeetingRecommendationBanner extends StatefulWidget {
  final bool alcoholFree;

  /// 노출 시간 (권장 2.5~3.5초).
  final Duration visibleDuration;

  final Duration fadeDuration;

  const BlindMeetingRecommendationBanner({
    super.key,
    required this.alcoholFree,
    this.visibleDuration = const Duration(milliseconds: 3000),
    this.fadeDuration = const Duration(milliseconds: 450),
  });

  @override
  State<BlindMeetingRecommendationBanner> createState() =>
      _BlindMeetingRecommendationBannerState();
}

class _BlindMeetingRecommendationBannerState
    extends State<BlindMeetingRecommendationBanner> {
  bool _visible = false;

  String get _message => widget.alcoholFree
      ? blindMeetingAlcoholFreeRecommendationMessage
      : blindMeetingRecommendationMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() => _visible = true);
      _scheduleHide();
    });
  }

  void _scheduleHide() {
    Future.delayed(widget.visibleDuration, () {
      if (!mounted) return;
      setState(() => _visible = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final reduceMotion =
        MediaQuery.maybeOf(context)?.disableAnimations ?? false;

    // liveRegion: screen reader가 배너 등장 시 내용을 읽어준다.
    final content = Semantics(
      liveRegion: true,
      label: _message.replaceAll('\n', ' '),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        decoration: BoxDecoration(
          color: palette.plum.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: palette.plum.withValues(alpha: 0.22)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              widget.alcoholFree
                  ? Icons.local_cafe_outlined
                  : Icons.favorite_border,
              size: 18,
              color: palette.plum,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: ExcludeSemantics(
                child: Text(
                  _message,
                  style: BlindMeetingText.caption(palette.ink),
                ),
              ),
            ),
          ],
        ),
      ),
    );

    if (reduceMotion) {
      // 모션 감소 설정에서는 fade 없이 표시하고, 시간이 지나면 조용히 사라진다.
      return _visible
          ? Padding(padding: const EdgeInsets.only(bottom: 16), child: content)
          : const SizedBox.shrink();
    }

    return AnimatedOpacity(
      opacity: _visible ? 1 : 0,
      duration: widget.fadeDuration,
      curve: Curves.easeInOut,
      child: AnimatedSize(
        duration: widget.fadeDuration,
        curve: Curves.easeInOut,
        child: _visible
            ? Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: content,
              )
            : const SizedBox(width: double.infinity, height: 0),
      ),
    );
  }
}
