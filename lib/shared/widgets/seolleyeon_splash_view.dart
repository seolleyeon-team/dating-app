import 'package:flutter/cupertino.dart';

/// The visual shared by the initial app splash and privacy covers.
class SeolleyeonSplashView extends StatelessWidget {
  const SeolleyeonSplashView({super.key});

  static const backgroundColor = Color(0xFFFAFAFA);
  static const accentColor = Color(0xFFFF6B8A);

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(
      color: backgroundColor,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '설레연',
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 36,
                fontWeight: FontWeight.w700,
                color: accentColor,
                decoration: TextDecoration.none,
              ),
            ),
            SizedBox(height: 16),
            CupertinoActivityIndicator(color: accentColor),
          ],
        ),
      ),
    );
  }
}
