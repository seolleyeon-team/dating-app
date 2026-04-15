import 'package:flutter/cupertino.dart';

class AppPrivacySplashOverlay extends StatefulWidget {
  final Widget child;

  const AppPrivacySplashOverlay({super.key, required this.child});

  @override
  State<AppPrivacySplashOverlay> createState() => _AppPrivacySplashOverlayState();
}

class _AppPrivacySplashOverlayState extends State<AppPrivacySplashOverlay>
    with WidgetsBindingObserver {
  AppLifecycleState? _lastLifecycleState;

  bool get _shouldShowOverlay {
    final state = _lastLifecycleState;
    return state == AppLifecycleState.inactive ||
        state == AppLifecycleState.hidden ||
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
            child: const _PrivacySplashView(),
          ),
        ),
      ],
    );
  }
}

class _PrivacySplashView extends StatelessWidget {
  const _PrivacySplashView();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(color: Color(0xFFFAFAFA)),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Text(
              '설레연',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 36,
                fontWeight: FontWeight.w800,
                color: Color(0xFFFF6B8A),
              ),
            ),
            SizedBox(height: 14),
            CupertinoActivityIndicator(color: Color(0xFFFF6B8A)),
          ],
        ),
      ),
    );
  }
}
