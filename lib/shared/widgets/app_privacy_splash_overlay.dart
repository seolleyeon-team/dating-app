import 'package:flutter/cupertino.dart';

import 'seolleyeon_splash_view.dart';

class AppPrivacySplashOverlay extends StatefulWidget {
  final Widget child;

  const AppPrivacySplashOverlay({super.key, required this.child});

  @override
  State<AppPrivacySplashOverlay> createState() =>
      _AppPrivacySplashOverlayState();
}

class _AppPrivacySplashOverlayState extends State<AppPrivacySplashOverlay>
    with WidgetsBindingObserver {
  AppLifecycleState? _lastLifecycleState;

  bool get _shouldShowOverlay {
    final state = _lastLifecycleState;
    // Do not cover on `inactive` alone.
    // KakaoTalk / Universal Link handoff briefly parks the app in
    // `inactive` on iPhone (incl. 15 Pro). Treating that as "hide UI"
    // leaves a stuck splash that looks like the screen turned off.
    return state == AppLifecycleState.hidden ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _lastLifecycleState = WidgetsBinding.instance.lifecycleState;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    setState(() {
      _lastLifecycleState = state;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        widget.child,
        IgnorePointer(
          ignoring: !_shouldShowOverlay,
          child: AnimatedOpacity(
            duration: const Duration(milliseconds: 140),
            opacity: _shouldShowOverlay ? 1 : 0,
            child: const SeolleyeonSplashView(),
          ),
        ),
      ],
    );
  }
}
