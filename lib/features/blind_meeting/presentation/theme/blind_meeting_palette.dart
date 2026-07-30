// =============================================================================
// 3:3 블라인드 취향 미팅 — 화면 팔레트
// 경로: lib/features/blind_meeting/presentation/theme/blind_meeting_palette.dart
//
// 방향: Quiet Romance / Clear Trust
//  - 따뜻한 off-white 배경
//  - plum / indigo 계열의 절제된 강조색
//  - muted rose, sage 보조색
//  - 부드러운 카드와 넉넉한 여백
//
// 시즌 미팅의 슬롯머신·네온·카지노 느낌을 쓰지 않는다.
// =============================================================================

import 'package:flutter/material.dart';

/// 블라인드 미팅 화면 전용 색 묶음.
class BlindMeetingPalette {
  final Color background;
  final Color surface;
  final Color surfaceMuted;
  final Color ink;
  final Color inkSoft;
  final Color inkFaint;
  final Color plum;
  final Color indigo;
  final Color mutedRose;
  final Color sage;
  final Color border;
  final Color overlay;

  const BlindMeetingPalette({
    required this.background,
    required this.surface,
    required this.surfaceMuted,
    required this.ink,
    required this.inkSoft,
    required this.inkFaint,
    required this.plum,
    required this.indigo,
    required this.mutedRose,
    required this.sage,
    required this.border,
    required this.overlay,
  });

  static const BlindMeetingPalette light = BlindMeetingPalette(
    background: Color(0xFFFBF8F6),
    surface: Color(0xFFFFFFFF),
    surfaceMuted: Color(0xFFF4EFEC),
    ink: Color(0xFF241E24),
    inkSoft: Color(0xFF6B5F66),
    inkFaint: Color(0xFF9A8F94),
    plum: Color(0xFF5B4A72),
    indigo: Color(0xFF3F4A6B),
    mutedRose: Color(0xFFC08A93),
    sage: Color(0xFF7E9484),
    border: Color(0xFFE8E0DC),
    overlay: Color(0x14241E24),
  );

  static const BlindMeetingPalette dark = BlindMeetingPalette(
    background: Color(0xFF17141A),
    surface: Color(0xFF211D25),
    surfaceMuted: Color(0xFF2A252F),
    ink: Color(0xFFF0EAEE),
    inkSoft: Color(0xFFB6ABB4),
    inkFaint: Color(0xFF8A7F88),
    plum: Color(0xFFB9A6D6),
    indigo: Color(0xFF9FAAD0),
    mutedRose: Color(0xFFD8A9B1),
    sage: Color(0xFF9DB6A5),
    border: Color(0xFF39323E),
    overlay: Color(0x33000000),
  );

  static BlindMeetingPalette of(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? dark : light;
}

/// 블라인드 미팅 화면 typography.
class BlindMeetingText {
  BlindMeetingText._();

  static const String fontFamily = 'Pretendard';

  static TextStyle display(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 26,
    height: 1.35,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.6,
    color: color,
  );

  static TextStyle title(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    height: 1.4,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.4,
    color: color,
  );

  static TextStyle sectionTitle(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 16,
    height: 1.45,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: color,
  );

  static TextStyle body(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 15,
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

  static TextStyle label(Color color) => TextStyle(
    fontFamily: fontFamily,
    fontSize: 11,
    height: 1.4,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.6,
    color: color,
  );
}

/// 화면 최대 너비 (Flutter Web에서 레이아웃이 늘어지지 않게 한다).
const double blindMeetingMaxContentWidth = 520;

/// 모바일 우선 + 웹에서 깨지지 않도록 가운데 정렬 컨테이너로 감싼다.
class BlindMeetingResponsiveBody extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const BlindMeetingResponsiveBody({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 20),
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
