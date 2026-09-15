import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

/// Keeps legacy white flows readable when the app-wide dark mode is enabled.
///
/// The email verification and profile-onboarding screens intentionally keep
/// their original white canvas and light palette.  Without this local theme,
/// uncoloured input text inherits the app's dark [TextTheme] and becomes white
/// on those white surfaces.
class LightSurfaceTheme extends StatelessWidget {
  const LightSurfaceTheme({required this.child, super.key});

  final Widget child;

  static const _primary = Color(0xFFFF6B8A);
  static const _background = Color(0xFFFAFAFA);
  static const _surface = Color(0xFFFFFFFF);
  static const _textPrimary = Color(0xFF0F172A);
  static const _textSecondary = Color(0xFF64748B);
  static const _textHint = Color(0xFF9CA3AF);

  @override
  Widget build(BuildContext context) {
    final base = ThemeData.light(useMaterial3: true);
    final textTheme = base.textTheme.apply(
      bodyColor: _textPrimary,
      displayColor: _textPrimary,
    );
    final materialTheme = base.copyWith(
      primaryColor: _primary,
      scaffoldBackgroundColor: _background,
      colorScheme: const ColorScheme.light(
        primary: _primary,
        secondary: _primary,
        surface: _surface,
        onPrimary: Colors.white,
        onSurface: _textPrimary,
        onSurfaceVariant: _textSecondary,
      ),
      textTheme: textTheme,
      appBarTheme: const AppBarTheme(
        backgroundColor: _background,
        foregroundColor: _textPrimary,
        elevation: 0,
      ),
      inputDecorationTheme: const InputDecorationTheme(
        hintStyle: TextStyle(color: _textHint),
        labelStyle: TextStyle(color: _textSecondary),
        floatingLabelStyle: TextStyle(color: _primary),
      ),
    );

    return Theme(
      data: materialTheme,
      child: CupertinoTheme(
        data: const CupertinoThemeData(
          brightness: Brightness.light,
          primaryColor: _primary,
          scaffoldBackgroundColor: _background,
          textTheme: CupertinoTextThemeData(
            textStyle: TextStyle(
              fontFamily: 'NanumSquareRound',
              color: _textPrimary,
            ),
          ),
        ),
        child: child,
      ),
    );
  }
}
