import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'services/navigation_service.dart';
import 'services/push_notification_service.dart';
import 'router/app_router.dart';
import 'router/route_names.dart';
import 'providers/auth_provider.dart';
import 'features/community/providers/community_provider.dart';

/// 설레연 앱 (MaterialApp 루트 + Provider 등록)
class SeolleyeonApp extends StatefulWidget {
  const SeolleyeonApp({super.key});

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
        ChangeNotifierProvider<AuthProvider>(
          create: (_) => AuthProvider(),
        ),
        ChangeNotifierProvider<CommunityProvider>(
          create: (ctx) => CommunityProvider(
            authProvider: ctx.read<AuthProvider>(),
          ),
        ),
      ],
      child: MaterialApp(
        navigatorKey: NavigationService.navigatorKey,
        title: '설레연',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          primaryColor: SeolleyeonApp.primaryColor,
          fontFamily: 'Noto Sans KR',
          textTheme: _textThemeWithoutUnderline(
            _applyFontWeight(
              ThemeData.light().textTheme.apply(
                fontFamily: 'Noto Sans KR',
              ),
            ),
          ),
          colorScheme: const ColorScheme.light(
            primary: SeolleyeonApp.primaryColor,
            secondary: SeolleyeonApp.primaryColor,
            surface: SeolleyeonApp.backgroundColor,
          ),
          scaffoldBackgroundColor: SeolleyeonApp.backgroundColor,
          appBarTheme: const AppBarTheme(
            backgroundColor: SeolleyeonApp.backgroundColor,
            foregroundColor: Color(0xFF0F172A),
            elevation: 0,
          ),
          inputDecorationTheme: InputDecorationTheme(
            hintStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
            labelStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
            floatingLabelStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
          ),
          elevatedButtonTheme: ElevatedButtonThemeData(
            style: ElevatedButton.styleFrom(
              textStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
            ),
          ),
          textButtonTheme: TextButtonThemeData(
            style: TextButton.styleFrom(
              textStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
            ),
          ),
          outlinedButtonTheme: OutlinedButtonThemeData(
            style: OutlinedButton.styleFrom(
              textStyle: const TextStyle(fontFamily: 'Noto Sans KR'),
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
                  .copyWith(fontFamily: 'Noto Sans KR'),
              navTitleTextStyle: CupertinoThemeData(brightness: Brightness.light)
                  .textTheme
                  .navTitleTextStyle
                  .copyWith(
                fontFamily: 'Noto Sans KR',
                fontWeight: FontWeight.w600,
              ),
              navLargeTitleTextStyle: CupertinoThemeData(
                brightness: Brightness.light,
              ).textTheme.navLargeTitleTextStyle.copyWith(
                fontFamily: 'Noto Sans KR',
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
        ),
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
      ),
    );
  }
}

/// 폰트 두께를 두 단계씩 굵게 (w400→w600, w500→w700 등)
TextTheme _applyFontWeight(TextTheme base) {
  TextStyle bolder(TextStyle? s) {
    if (s == null) return const TextStyle();
    final w = s.fontWeight ?? FontWeight.w400;
    final nextIndex = (w.index + 2).clamp(0, FontWeight.w900.index);
    return s.copyWith(fontWeight: FontWeight.values[nextIndex]);
  }
  return TextTheme(
    displayLarge: bolder(base.displayLarge),
    displayMedium: bolder(base.displayMedium),
    displaySmall: bolder(base.displaySmall),
    headlineLarge: bolder(base.headlineLarge),
    headlineMedium: bolder(base.headlineMedium),
    headlineSmall: bolder(base.headlineSmall),
    titleLarge: bolder(base.titleLarge),
    titleMedium: bolder(base.titleMedium),
    titleSmall: bolder(base.titleSmall),
    bodyLarge: bolder(base.bodyLarge),
    bodyMedium: bolder(base.bodyMedium),
    bodySmall: bolder(base.bodySmall),
    labelLarge: bolder(base.labelLarge),
    labelMedium: bolder(base.labelMedium),
    labelSmall: bolder(base.labelSmall),
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
