import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants/app_colors.dart';
import 'services/navigation_service.dart';
import 'services/push_notification_service.dart';
import 'router/app_router.dart';
import 'router/route_names.dart';
import 'providers/auth_provider.dart';
import 'providers/theme_provider.dart';
import 'features/community/providers/community_provider.dart';

/// 설레연 앱 (MaterialApp 루트 + Provider 등록)
class SeolleyeonApp extends StatefulWidget {
  const SeolleyeonApp({super.key});

  static const String fontFamily = 'Pretendard';

  static const Color primaryColor = Color(0xFFFF6B8A);
  static const Color backgroundColor = Color(0xFFFAFAFA);

  @override
  State<SeolleyeonApp> createState() => _SeolleyeonAppState();
}

class _SeolleyeonAppState extends State<SeolleyeonApp> {
  @override
  void initState() {
    super.initState();
    PushNotificationService.instance.initialize();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<ThemeProvider>(
          create: (_) => ThemeProvider(),
        ),
        ChangeNotifierProvider<AuthProvider>(
          create: (_) => AuthProvider(),
        ),
        ChangeNotifierProvider<CommunityProvider>(
          create: (ctx) => CommunityProvider(
            authProvider: ctx.read<AuthProvider>(),
          ),
        ),
      ],
      child: Consumer<ThemeProvider>(
        builder: (context, themeProvider, _) {
          return MaterialApp(
            navigatorKey: NavigationService.navigatorKey,
            title: '설레연',
            debugShowCheckedModeBanner: false,
            themeMode: themeProvider.themeMode,
            theme: _buildLightTheme(),
            darkTheme: _buildDarkTheme(),
            initialRoute: RouteNames.splash,
            onGenerateRoute: AppRouter.generateRoute,
            builder: (context, child) {
              final theme = Theme.of(context);
              final fallback =
                  theme.textTheme.bodyMedium ??
                  const TextStyle(decoration: TextDecoration.none);

              return DefaultTextStyle(
                style: fallback.copyWith(decoration: TextDecoration.none),
                child: child ?? const SizedBox.shrink(),
              );
            },
          );
        },
      ),
    );
  }

  ThemeData _buildLightTheme() {
    return ThemeData(
      useMaterial3: true,
      primaryColor: SeolleyeonApp.primaryColor,
      fontFamily: SeolleyeonApp.fontFamily,
      brightness: Brightness.light,
      textTheme: _textThemeWithoutUnderline(
        _applyFontWeight(
          ThemeData.light().textTheme.apply(
            fontFamily: SeolleyeonApp.fontFamily,
          ),
        ),
      ),
      colorScheme: const ColorScheme.light(
        primary: SeolleyeonApp.primaryColor,
        secondary: SeolleyeonApp.primaryColor,
        surface: SeolleyeonApp.backgroundColor,
      ),
      scaffoldBackgroundColor: SeolleyeonApp.backgroundColor,
      appBarTheme: AppBarTheme(
        backgroundColor: SeolleyeonApp.backgroundColor,
        foregroundColor: const Color(0xFF0F172A),
        elevation: 0,
        titleTextStyle: TextStyle(
          fontFamily: SeolleyeonApp.fontFamily,
          fontWeight: FontWeight.w700,
          fontSize: 18,
          color: const Color(0xFF0F172A),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        hintStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        labelStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        floatingLabelStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      cupertinoOverrideTheme: CupertinoThemeData(
        primaryColor: SeolleyeonApp.primaryColor,
        brightness: Brightness.light,
        scaffoldBackgroundColor: SeolleyeonApp.backgroundColor,
        textTheme: CupertinoThemeData(brightness: Brightness.light)
            .textTheme
            .copyWith(
          textStyle: CupertinoThemeData(brightness: Brightness.light)
              .textTheme
              .textStyle
              .copyWith(fontFamily: SeolleyeonApp.fontFamily),
          navTitleTextStyle: CupertinoThemeData(brightness: Brightness.light)
              .textTheme
              .navTitleTextStyle
              .copyWith(
            fontFamily: SeolleyeonApp.fontFamily,
            fontWeight: FontWeight.w600,
          ),
          navLargeTitleTextStyle: CupertinoThemeData(
            brightness: Brightness.light,
          ).textTheme.navLargeTitleTextStyle.copyWith(
            fontFamily: SeolleyeonApp.fontFamily,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: CupertinoPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        },
      ),
      extensions: const <ThemeExtension>[
        SeolThemeColors.light,
      ],
    );
  }

  ThemeData _buildDarkTheme() {
    const darkBg = AppColorsDark.background;
    const darkSurface = AppColorsDark.surface;
    const darkText = AppColorsDark.textPrimary;
    const darkPrimary = AppColorsDark.primary;

    return ThemeData(
      useMaterial3: true,
      primaryColor: darkPrimary,
      fontFamily: SeolleyeonApp.fontFamily,
      brightness: Brightness.dark,
      textTheme: _textThemeWithoutUnderline(
        _applyFontWeight(
          ThemeData.dark().textTheme.apply(
            fontFamily: SeolleyeonApp.fontFamily,
            bodyColor: darkText,
            displayColor: darkText,
          ),
        ),
      ),
      colorScheme: const ColorScheme.dark(
        primary: darkPrimary,
        secondary: AppColorsDark.primaryLight,
        surface: darkSurface,
        error: AppColorsDark.error,
        onPrimary: Color(0xFFF0E8ED),
        onSurface: darkText,
      ),
      scaffoldBackgroundColor: darkBg,
      appBarTheme: AppBarTheme(
        backgroundColor: darkSurface,
        foregroundColor: darkText,
        elevation: 0,
        titleTextStyle: TextStyle(
          fontFamily: SeolleyeonApp.fontFamily,
          fontWeight: FontWeight.w700,
          fontSize: 18,
          color: darkText,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        hintStyle: TextStyle(
          fontFamily: SeolleyeonApp.fontFamily,
          color: AppColorsDark.textHint,
        ),
        labelStyle: TextStyle(
          fontFamily: SeolleyeonApp.fontFamily,
          color: AppColorsDark.textSecondary,
        ),
        floatingLabelStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: darkPrimary,
          foregroundColor: const Color(0xFFF0E8ED),
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: darkPrimary,
          side: const BorderSide(color: darkPrimary),
          textStyle: TextStyle(fontFamily: SeolleyeonApp.fontFamily),
        ),
      ),
      cupertinoOverrideTheme: CupertinoThemeData(
        primaryColor: darkPrimary,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: darkBg,
        barBackgroundColor: darkSurface.withValues(alpha: 0.9),
        textTheme: CupertinoThemeData(brightness: Brightness.dark)
            .textTheme
            .copyWith(
          textStyle: CupertinoThemeData(brightness: Brightness.dark)
              .textTheme
              .textStyle
              .copyWith(
            fontFamily: SeolleyeonApp.fontFamily,
            color: darkText,
          ),
          navTitleTextStyle: CupertinoThemeData(brightness: Brightness.dark)
              .textTheme
              .navTitleTextStyle
              .copyWith(
            fontFamily: SeolleyeonApp.fontFamily,
            fontWeight: FontWeight.w600,
            color: darkText,
          ),
          navLargeTitleTextStyle: CupertinoThemeData(
            brightness: Brightness.dark,
          ).textTheme.navLargeTitleTextStyle.copyWith(
            fontFamily: SeolleyeonApp.fontFamily,
            fontWeight: FontWeight.w700,
            color: darkText,
          ),
        ),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: darkSurface,
        titleTextStyle: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: darkText,
        ),
        contentTextStyle: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 14,
          color: AppColorsDark.textSecondary,
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: darkSurface,
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: CupertinoPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        },
      ),
      extensions: const <ThemeExtension>[
        SeolThemeColors.dark,
      ],
    );
  }
}

/// 제목·헤드라인은 더 굵게, 본문·라벨은 한 단계만 (가독성)
TextTheme _applyFontWeight(TextTheme base) {
  TextStyle bump(TextStyle? s, int steps) {
    if (s == null) return const TextStyle();
    final w = s.fontWeight ?? FontWeight.w400;
    final nextIndex = (w.index + steps).clamp(0, FontWeight.w900.index);
    return s.copyWith(fontWeight: FontWeight.values[nextIndex]);
  }

  return TextTheme(
    displayLarge: bump(base.displayLarge, 2),
    displayMedium: bump(base.displayMedium, 2),
    displaySmall: bump(base.displaySmall, 2),
    headlineLarge: bump(base.headlineLarge, 2),
    headlineMedium: bump(base.headlineMedium, 2),
    headlineSmall: bump(base.headlineSmall, 2),
    titleLarge: bump(base.titleLarge, 2),
    titleMedium: bump(base.titleMedium, 2),
    titleSmall: bump(base.titleSmall, 1),
    bodyLarge: bump(base.bodyLarge, 1),
    bodyMedium: bump(base.bodyMedium, 1),
    bodySmall: bump(base.bodySmall, 1),
    labelLarge: bump(base.labelLarge, 1),
    labelMedium: bump(base.labelMedium, 1),
    labelSmall: bump(base.labelSmall, 0),
  );
}

/// 텍스트 테마 전체에 밑줄 제거 적용
TextTheme _textThemeWithoutUnderline(TextTheme base) {
  TextStyle noUnderline(TextStyle? s) => s == null
      ? const TextStyle(decoration: TextDecoration.none)
      : s.copyWith(decoration: TextDecoration.none);

  return TextTheme(
    displayLarge: noUnderline(base.displayLarge),
    displayMedium: noUnderline(base.displayMedium),
    displaySmall: noUnderline(base.displaySmall),
    headlineLarge: noUnderline(base.headlineLarge),
    headlineMedium: noUnderline(base.headlineMedium),
    headlineSmall: noUnderline(base.headlineSmall),
    titleLarge: noUnderline(base.titleLarge),
    titleMedium: noUnderline(base.titleMedium),
    titleSmall: noUnderline(base.titleSmall),
    bodyLarge: noUnderline(base.bodyLarge),
    bodyMedium: noUnderline(base.bodyMedium),
    bodySmall: noUnderline(base.bodySmall),
    labelLarge: noUnderline(base.labelLarge),
    labelMedium: noUnderline(base.labelMedium),
    labelSmall: noUnderline(base.labelSmall),
  );
}
