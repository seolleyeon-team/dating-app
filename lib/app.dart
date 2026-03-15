import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
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
          fontFamily: GoogleFonts.notoSansKr().fontFamily ?? 'Noto Sans KR',
          textTheme: _textThemeWithoutUnderline(
            GoogleFonts.notoSansKrTextTheme(ThemeData.light().textTheme),
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
          cupertinoOverrideTheme: const CupertinoThemeData(
            primaryColor: SeolleyeonApp.primaryColor,
            brightness: Brightness.light,
            scaffoldBackgroundColor: SeolleyeonApp.backgroundColor,
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
