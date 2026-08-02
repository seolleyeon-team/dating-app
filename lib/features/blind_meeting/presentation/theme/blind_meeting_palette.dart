// =============================================================================
// 3:3 블라인드 취향 미팅 — 화면 팔레트
// 경로: lib/features/blind_meeting/presentation/theme/blind_meeting_palette.dart
//
// 이 팔레트는 독립 테마가 아니다.
// 이벤트 탭(3:3 시즌 미팅)과 같은 디자인 시스템을 쓰기 위해
// ThemeData / SeolThemeColors 토큰을 블라인드 미팅 화면에서 쓰는
// 의미 이름으로만 다시 묶어주는 어댑터다.
//
//  background   → seol.eventBackground (연한 핑크 오프화이트)
//  surface      → seol.cardSurface
//  surfaceMuted → seol.pink50 (카드 안 서브패널)
//  accent       → colorScheme.primary (설레연 코랄 핑크)
//
// 색을 바꿔야 할 때는 이 파일이 아니라 SeolThemeColors / ColorScheme를 고친다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../core/constants/app_colors.dart';

/// 블라인드 미팅 화면이 쓰는 색 묶음 (설레연 이벤트 테마에서 파생).
class BlindMeetingPalette {
  /// 화면 배경 — 이벤트 탭 캔버스와 동일.
  final Color background;

  /// 카드 배경.
  final Color surface;

  /// 카드 안 서브패널 배경 (연한 핑크 박스).
  final Color surfaceMuted;

  /// 제목 텍스트.
  final Color ink;

  /// 본문 텍스트.
  final Color inkSoft;

  /// 보조 설명 텍스트.
  final Color inkFaint;

  /// 메인 포인트 — CTA, 선택 상태, 포인트 아이콘.
  final Color accent;

  /// 짙은 로즈 포인트 — 상대 팀 등 같은 계열의 두 번째 톤.
  final Color accentDeep;

  /// 연한 로즈 배경 위에서 읽혀야 하는 텍스트 — 보완·주의 안내, 비활성 CTA 라벨.
  final Color attention;

  /// 완료·긍정 표시.
  final Color positive;

  /// 카드/패널 외곽선.
  final Color border;

  /// 카드 그림자 (핑크 기운의 소프트 섀도).
  final Color overlay;

  const BlindMeetingPalette({
    required this.background,
    required this.surface,
    required this.surfaceMuted,
    required this.ink,
    required this.inkSoft,
    required this.inkFaint,
    required this.accent,
    required this.accentDeep,
    required this.attention,
    required this.positive,
    required this.border,
    required this.overlay,
  });

  /// 설레연 테마 토큰으로 팔레트를 구성한다.
  factory BlindMeetingPalette.fromTokens({
    required SeolThemeColors seol,
    required Color primary,
    required Color primaryDark,
    required bool isDark,
  }) {
    return BlindMeetingPalette(
      background: seol.eventBackground,
      surface: seol.cardSurface,
      surfaceMuted: seol.pink50,
      ink: seol.gray800,
      inkSoft: seol.bodyText,
      inkFaint: seol.sectionTitle,
      accent: primary,
      accentDeep: primaryDark,
      attention: seol.rose700,
      positive: seol.emerald700,
      border: seol.eventBorder,
      // 시즌 미팅 히어로 카드와 같은 핑크 기운의 그림자.
      overlay: isDark
          ? Colors.black.withValues(alpha: 0.4)
          : primary.withValues(alpha: 0.12),
    );
  }

  /// 테마 확장이 없는 컨텍스트(위젯 테스트 등)를 위한 라이트 기본값.
  static final BlindMeetingPalette light = BlindMeetingPalette.fromTokens(
    seol: SeolThemeColors.light,
    primary: AppColors.primary,
    primaryDark: AppColors.primaryDark,
    isDark: false,
  );

  /// 테마 확장이 없는 컨텍스트를 위한 다크 기본값.
  static final BlindMeetingPalette dark = BlindMeetingPalette.fromTokens(
    seol: SeolThemeColors.dark,
    primary: AppColorsDark.primary,
    primaryDark: AppColorsDark.primaryDark,
    isDark: true,
  );

  static BlindMeetingPalette of(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final seol = theme.extension<SeolThemeColors>();
    if (seol == null) return isDark ? dark : light;

    return BlindMeetingPalette.fromTokens(
      seol: seol,
      primary: theme.colorScheme.primary,
      primaryDark: isDark ? AppColorsDark.primaryDark : AppColors.primaryDark,
      isDark: isDark,
    );
  }
}

/// 블라인드 미팅 화면 typography — 이벤트 탭 텍스트 위계와 같은 스케일.
class BlindMeetingText {
  BlindMeetingText._();

  static const String fontFamily = 'Pretendard';

  /// 히어로 카드 타이틀 (시즌 미팅 '두근두근 3:3 시즌 미팅'과 동일 위계).
  static TextStyle display(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 22,
    height: 1.35,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: color,
  );

  static TextStyle title(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    height: 1.4,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: color,
  );

  /// 카드 안 항목 제목 (시즌 미팅 장소 카드 이름과 동일 위계).
  static TextStyle cardTitle(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 15,
    height: 1.4,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: color,
  );

  /// 섹션 헤더 (시즌 미팅 '제휴 장소 추천'과 동일 위계).
  static TextStyle sectionTitle(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 18,
    height: 1.4,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
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
    fontSize: 13,
    height: 1.5,
    fontWeight: FontWeight.w500,
    color: color,
  );

  /// pill / badge 라벨 (시즌 미팅 'SAFE MATCHING' 배지와 동일 위계).
  static TextStyle label(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 12,
    height: 1.3,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.2,
    color: color,
  );
}

// =============================================================================
// 이벤트 탭 공통 형태 토큰 — 시즌 미팅 화면에서 추출한 값
// =============================================================================

/// 히어로 카드 radius (시즌 미팅 슬롯머신 카드).
const double kEventHeroRadius = 32;

/// 일반 카드 / 서브패널 radius (상태 표시줄, 장소 카드, 슬롯 박스).
const double kEventCardRadius = 20;

/// 메인 CTA 높이.
const double kEventCtaHeight = 56;

/// 이벤트 탭 좌우 여백.
const double kEventHorizontalPadding = 16;

/// 권장 선택 날짜 수.
///
/// 매칭 시뮬레이션에서 pool 120명 기준 1개 42% → 2개 75% → 3개 85% → 5개 93%로
/// 3개 이후 증가폭이 급격히 줄어든다. 강제 조건이 아니라 권장 안내에만 쓴다.
const int kRecommendedDateCount = 3;

/// 화면 최대 너비 (Flutter Web에서 레이아웃이 늘어지지 않게 한다).
const double blindMeetingMaxContentWidth = 520;

/// 모바일 우선 + 웹에서 깨지지 않도록 가운데 정렬 컨테이너로 감싼다.
class BlindMeetingResponsiveBody extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const BlindMeetingResponsiveBody({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.symmetric(
      horizontal: kEventHorizontalPadding,
    ),
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: blindMeetingMaxContentWidth,
        ),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}
