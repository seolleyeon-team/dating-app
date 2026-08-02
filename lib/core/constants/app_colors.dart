import 'package:flutter/material.dart';

/// 설레연 앱 color 시스템
class AppColors {
  AppColors._();

  // Primary Colors
  static const Color primary = Color(0xFFFF6B8A);
  static const Color primaryLight = Color(0xFFFF8FA8);
  static const Color primaryDark = Color(0xFFE84A6A);

  // Background Colors
  static const Color background = Color(0xFFF8F9FA);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceVariant = Color(0xFFF5F5F5);

  // Text Colors
  static const Color textPrimary = Color(0xFF1A1A1A);
  static const Color textSecondary = Color(0xFF666666);
  static const Color textHint = Color(0xFFAAAAAA);

  // Status Colors
  static const Color success = Color(0xFF4CAF50);
  static const Color warning = Color(0xFFFF9800);
  static const Color error = Color(0xFFF44336);

  // Heart Colors
  static const Color heart = Color(0xFFFF4757);
  static const Color heartLight = Color(0xFFFFE8EA);

  // Chat Colors
  static const Color chatBubbleMine = Color(0xFFFF6B8A);
  static const Color chatBubbleOther = Color(0xFFEEEEEE);

  // Border & Divider
  static const Color border = Color(0xFFE0E0E0);
  static const Color divider = Color(0xFFF0F0F0);
}

/// 설레연 다크모드 색상 — Quiet Romance / Clear Trust 톤
class AppColorsDark {
  AppColorsDark._();

  // Primary Colors (브랜드 톤 유지, 약간 부드럽게)
  static const Color primary = Color(0xFFFF7B96);
  static const Color primaryLight = Color(0xFFFF9DB3);
  static const Color primaryDark = Color(0xFFD4546E);

  // Background — deep plum / warm charcoal
  static const Color background = Color(0xFF1C1520);
  static const Color surface = Color(0xFF261E2C);
  static const Color surfaceVariant = Color(0xFF302838);

  // Text — soft ivory-lilac
  static const Color textPrimary = Color(0xFFF0E8ED);
  static const Color textSecondary = Color(0xFFB0A0AC);
  static const Color textHint = Color(0xFF7A6B76);

  // Status (약간 밝게 조정)
  static const Color success = Color(0xFF66BB6A);
  static const Color warning = Color(0xFFFFB74D);
  static const Color error = Color(0xFFEF7070);

  // Heart
  static const Color heart = Color(0xFFFF6B7A);
  static const Color heartLight = Color(0xFF3D2830);

  // Chat
  static const Color chatBubbleMine = Color(0xFFFF7B96);
  static const Color chatBubbleOther = Color(0xFF352D3C);

  // Border & Divider — low-contrast cool plum-gray
  static const Color border = Color(0xFF3E3548);
  static const Color divider = Color(0xFF342C3C);
}

/// ThemeExtension: 화면별 _AppColors 대신 context에서 접근 가능한 토큰
class SeolThemeColors extends ThemeExtension<SeolThemeColors> {
  final Color cardSurface;
  final Color navBarBackground;
  final Color sectionTitle;
  final Color settingsIcon;
  final Color gray100;
  final Color gray200;
  final Color gray300;
  final Color gray400;
  final Color gray800;
  final Color pink50;
  final Color purple50;
  final Color purple500;
  final Color emerald50;
  final Color emerald500;
  final Color kakao;
  final Color kakaoBrown;

  // ── 이벤트 탭 공통 토큰 ──────────────────────────────────────────────
  // 3:3 시즌 미팅 / 블라인드 취향 미팅이 같은 캔버스를 쓰도록 공용화한다.

  /// 이벤트 탭 배경 (연한 핑크 오프화이트)
  final Color eventBackground;

  /// 이벤트 탭 카드/패널 외곽선 (웜 로즈 그레이)
  final Color eventBorder;

  /// 본문 / 비활성 탭 라벨용 중간 회색 (sectionTitle보다 진해 읽힌다)
  final Color bodyText;

  /// 본문 크기 텍스트에 쓸 수 있는 짙은 로즈 (주의·보완 안내)
  final Color rose700;

  /// 본문 크기 텍스트에 쓸 수 있는 짙은 에메랄드 (완료·긍정)
  final Color emerald700;

  const SeolThemeColors({
    required this.cardSurface,
    required this.navBarBackground,
    required this.sectionTitle,
    required this.settingsIcon,
    required this.gray100,
    required this.gray200,
    required this.gray300,
    required this.gray400,
    required this.gray800,
    required this.pink50,
    required this.purple50,
    required this.purple500,
    required this.emerald50,
    required this.emerald500,
    required this.kakao,
    required this.kakaoBrown,
    required this.eventBackground,
    required this.eventBorder,
    required this.bodyText,
    required this.rose700,
    required this.emerald700,
  });

  static const light = SeolThemeColors(
    cardSurface: Color(0xFFFFFFFF),
    navBarBackground: Color(0xFFFFFFFF),
    sectionTitle: Color(0xFF9CA3AF),
    settingsIcon: Color(0xFF1F2937),
    gray100: Color(0xFFF3F4F6),
    gray200: Color(0xFFE5E7EB),
    gray300: Color(0xFFD1D5DB),
    gray400: Color(0xFF9CA3AF),
    gray800: Color(0xFF1F2937),
    pink50: Color(0xFFFDF2F8),
    purple50: Color(0xFFFAF5FF),
    purple500: Color(0xFF8B5CF6),
    emerald50: Color(0xFFECFDF5),
    emerald500: Color(0xFF10B981),
    kakao: Color(0xFFFEE500),
    kakaoBrown: Color(0xFF3C1E1E),
    eventBackground: Color(0xFFFFF5F8),
    eventBorder: Color(0xFFE6DBDE),
    bodyText: Color(0xFF666666),
    rose700: Color(0xFFC2185B),
    emerald700: Color(0xFF047857),
  );

  static const dark = SeolThemeColors(
    cardSurface: Color(0xFF261E2C),
    navBarBackground: Color(0xFF221A28),
    sectionTitle: Color(0xFF7A6B76),
    settingsIcon: Color(0xFFD4C8D0),
    gray100: Color(0xFF302838),
    gray200: Color(0xFF3E3548),
    gray300: Color(0xFF4A4054),
    gray400: Color(0xFF7A6B76),
    gray800: Color(0xFFE0D6DC),
    pink50: Color(0xFF2E1F28),
    purple50: Color(0xFF271E30),
    purple500: Color(0xFFA78BFA),
    emerald50: Color(0xFF1A2922),
    emerald500: Color(0xFF34D399),
    kakao: Color(0xFFFEE500),
    kakaoBrown: Color(0xFF3C1E1E),
    eventBackground: Color(0xFF1C1520),
    eventBorder: Color(0xFF3E3548),
    bodyText: Color(0xFFB0A0AC),
    rose700: Color(0xFFF7A8C0),
    emerald700: Color(0xFF6EE7B7),
  );

  @override
  SeolThemeColors copyWith({
    Color? cardSurface,
    Color? navBarBackground,
    Color? sectionTitle,
    Color? settingsIcon,
    Color? gray100,
    Color? gray200,
    Color? gray300,
    Color? gray400,
    Color? gray800,
    Color? pink50,
    Color? purple50,
    Color? purple500,
    Color? emerald50,
    Color? emerald500,
    Color? kakao,
    Color? kakaoBrown,
    Color? eventBackground,
    Color? eventBorder,
    Color? bodyText,
    Color? rose700,
    Color? emerald700,
  }) {
    return SeolThemeColors(
      cardSurface: cardSurface ?? this.cardSurface,
      navBarBackground: navBarBackground ?? this.navBarBackground,
      sectionTitle: sectionTitle ?? this.sectionTitle,
      settingsIcon: settingsIcon ?? this.settingsIcon,
      gray100: gray100 ?? this.gray100,
      gray200: gray200 ?? this.gray200,
      gray300: gray300 ?? this.gray300,
      gray400: gray400 ?? this.gray400,
      gray800: gray800 ?? this.gray800,
      pink50: pink50 ?? this.pink50,
      purple50: purple50 ?? this.purple50,
      purple500: purple500 ?? this.purple500,
      emerald50: emerald50 ?? this.emerald50,
      emerald500: emerald500 ?? this.emerald500,
      kakao: kakao ?? this.kakao,
      kakaoBrown: kakaoBrown ?? this.kakaoBrown,
      eventBackground: eventBackground ?? this.eventBackground,
      eventBorder: eventBorder ?? this.eventBorder,
      bodyText: bodyText ?? this.bodyText,
      rose700: rose700 ?? this.rose700,
      emerald700: emerald700 ?? this.emerald700,
    );
  }

  @override
  SeolThemeColors lerp(
    covariant ThemeExtension<SeolThemeColors>? other,
    double t,
  ) {
    if (other is! SeolThemeColors) return this;
    return SeolThemeColors(
      cardSurface: Color.lerp(cardSurface, other.cardSurface, t)!,
      navBarBackground: Color.lerp(
        navBarBackground,
        other.navBarBackground,
        t,
      )!,
      sectionTitle: Color.lerp(sectionTitle, other.sectionTitle, t)!,
      settingsIcon: Color.lerp(settingsIcon, other.settingsIcon, t)!,
      gray100: Color.lerp(gray100, other.gray100, t)!,
      gray200: Color.lerp(gray200, other.gray200, t)!,
      gray300: Color.lerp(gray300, other.gray300, t)!,
      gray400: Color.lerp(gray400, other.gray400, t)!,
      gray800: Color.lerp(gray800, other.gray800, t)!,
      pink50: Color.lerp(pink50, other.pink50, t)!,
      purple50: Color.lerp(purple50, other.purple50, t)!,
      purple500: Color.lerp(purple500, other.purple500, t)!,
      emerald50: Color.lerp(emerald50, other.emerald50, t)!,
      emerald500: Color.lerp(emerald500, other.emerald500, t)!,
      kakao: Color.lerp(kakao, other.kakao, t)!,
      kakaoBrown: Color.lerp(kakaoBrown, other.kakaoBrown, t)!,
      eventBackground: Color.lerp(eventBackground, other.eventBackground, t)!,
      eventBorder: Color.lerp(eventBorder, other.eventBorder, t)!,
      bodyText: Color.lerp(bodyText, other.bodyText, t)!,
      rose700: Color.lerp(rose700, other.rose700, t)!,
      emerald700: Color.lerp(emerald700, other.emerald700, t)!,
    );
  }
}
