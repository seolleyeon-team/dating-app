// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 화면 팔레트
// 경로: lib/features/event/meeting_icebreaker/presentation/meeting_icebreaker_palette.dart
//
// blind_meeting_palette.dart와 같은 어댑터 방식이다.
// 독립 테마를 만들지 않고 SeolThemeColors / ColorScheme 토큰을 룰렛에서 쓰는
// 의미 이름으로 다시 묶는다. 색을 바꿔야 하면 이 파일이 아니라 토큰을 고친다.
//
// 카지노·도박 앱처럼 보이지 않도록 검정·네온·보라 대신
// warm off-white / soft pink / coral rose / muted rose / 연한 sage 를 쓴다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../core/constants/app_colors.dart';

class MeetingIcebreakerPalette {
  const MeetingIcebreakerPalette({
    required this.background,
    required this.surface,
    required this.surfaceMuted,
    required this.ink,
    required this.inkSoft,
    required this.inkFaint,
    required this.accent,
    required this.accentDeep,
    required this.rim,
    required this.rimShadow,
    required this.rimHighlight,
    required this.bulbOff,
    required this.bulbOn,
    required this.segmentLight,
    required this.segmentPink,
    required this.segmentWinner,
    required this.sage,
    required this.border,
    required this.shadow,
  });

  /// 팝업 배경 (이벤트 탭 캔버스와 같은 톤).
  final Color background;

  /// 카드 배경.
  final Color surface;

  /// 카드 안 서브패널 (연한 핑크 박스).
  final Color surfaceMuted;

  /// 제목 텍스트 (진한 navy/charcoal).
  final Color ink;

  /// 본문 텍스트.
  final Color inkSoft;

  /// 보조 설명 텍스트.
  final Color inkFaint;

  /// 메인 포인트 (coral rose).
  final Color accent;

  /// 짙은 로즈 (바늘, 강조 테두리).
  final Color accentDeep;

  /// 두꺼운 외곽 rim.
  final Color rim;

  /// rim 아래쪽 그림자 (입체감).
  final Color rimShadow;

  /// rim 위쪽 하이라이트 (입체감).
  final Color rimHighlight;

  /// 꺼진 전구.
  final Color bulbOff;

  /// 켜진 전구.
  final Color bulbOn;

  /// 밝은 칸 (warm off-white).
  final Color segmentLight;

  /// 분홍 칸 (soft pink).
  final Color segmentPink;

  /// 당첨 칸.
  final Color segmentWinner;

  /// 중립 accent (연한 sage) — 안내 박스 등에 쓴다.
  final Color sage;

  /// 카드 외곽선.
  final Color border;

  /// 카드 그림자.
  final Color shadow;

  factory MeetingIcebreakerPalette.fromTokens({
    required SeolThemeColors seol,
    required Color primary,
    required Color primaryDark,
    required bool isDark,
  }) {
    return MeetingIcebreakerPalette(
      background: seol.eventBackground,
      surface: seol.cardSurface,
      surfaceMuted: seol.pink50,
      ink: seol.gray800,
      inkSoft: seol.bodyText,
      inkFaint: seol.sectionTitle,
      accent: primary,
      accentDeep: primaryDark,
      rim: isDark ? const Color(0xFF4A3340) : const Color(0xFFF3C4D3),
      rimShadow: isDark ? const Color(0xFF2E1F28) : const Color(0xFFD98CA6),
      rimHighlight: isDark ? const Color(0xFF60414F) : const Color(0xFFFFF0F5),
      bulbOff: isDark ? const Color(0xFF6B4C58) : const Color(0xFFFAE3EA),
      bulbOn: isDark ? const Color(0xFFFFC9D8) : const Color(0xFFFFFFFF),
      segmentLight: isDark ? const Color(0xFF352B3A) : const Color(0xFFFFFBF7),
      segmentPink: isDark ? const Color(0xFF4A3040) : const Color(0xFFFFE1EB),
      segmentWinner: isDark ? const Color(0xFF7A4359) : const Color(0xFFFFC8D9),
      sage: isDark ? const Color(0xFF2C3A33) : const Color(0xFFE7F1E9),
      border: seol.eventBorder,
      shadow: isDark
          ? Colors.black.withValues(alpha: 0.45)
          : primary.withValues(alpha: 0.14),
    );
  }

  /// 테마 확장이 없는 컨텍스트(위젯 테스트 등)를 위한 기본값.
  static final MeetingIcebreakerPalette light =
      MeetingIcebreakerPalette.fromTokens(
        seol: SeolThemeColors.light,
        primary: AppColors.primary,
        primaryDark: AppColors.primaryDark,
        isDark: false,
      );

  static final MeetingIcebreakerPalette dark =
      MeetingIcebreakerPalette.fromTokens(
        seol: SeolThemeColors.dark,
        primary: AppColorsDark.primary,
        primaryDark: AppColorsDark.primaryDark,
        isDark: true,
      );

  static MeetingIcebreakerPalette of(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final seol = theme.extension<SeolThemeColors>();
    if (seol == null) return isDark ? dark : light;
    return MeetingIcebreakerPalette.fromTokens(
      seol: seol,
      primary: theme.colorScheme.primary,
      primaryDark: isDark ? AppColorsDark.primaryDark : AppColors.primaryDark,
      isDark: isDark,
    );
  }
}

/// 룰렛 화면 typography (이벤트 탭 위계와 동일 스케일).
class MeetingIcebreakerText {
  MeetingIcebreakerText._();

  static const String fontFamily = 'Pretendard';

  static TextStyle title(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    height: 1.35,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: color,
  );

  static TextStyle body(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 14,
    height: 1.6,
    fontWeight: FontWeight.w500,
    color: color,
  );

  static TextStyle caption(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 12.5,
    height: 1.5,
    fontWeight: FontWeight.w500,
    color: color,
  );

  static TextStyle segment(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 11.5,
    height: 1.15,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: color,
  );

  static TextStyle resultTitle(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 22,
    height: 1.3,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: color,
  );

  static TextStyle resultNumber(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 40,
    height: 1.1,
    fontWeight: FontWeight.w700,
    color: color,
  );

  static TextStyle cta(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 16,
    height: 1.2,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: color,
  );
}

/// 룰렛 팝업 형태 토큰 (이벤트 탭 값과 동일).
const double kMeetingIcebreakerDialogRadius = 28;
const double kMeetingIcebreakerCardRadius = 20;
const double kMeetingIcebreakerCtaHeight = 56;
const double kMeetingIcebreakerMaxWidth = 420;
