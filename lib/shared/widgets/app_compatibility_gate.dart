import 'package:flutter/material.dart';

import '../../core/compatibility/app_compatibility.dart';
import '../../core/compatibility/app_compatibility_service.dart';
import '../../features/compatibility/required_update_screen.dart';

/// 업데이트가 필요한 빌드에서 본 화면 진입을 막는다.
///
/// `MaterialApp.builder` 에 놓는다. 그 자리는 Navigator **위**라서 여기서
/// 덮으면 어떤 경로로 들어온 화면이든 함께 덮인다 — 딥링크로 push 된 라우트도,
/// 푸시 알림이 `pushNamedAndRemoveUntil` 로 밀어넣은 라우트도 이 아래에 깔린다.
/// 라우트마다 가드를 붙이는 방식이었다면 새 화면을 추가할 때마다 빠뜨릴 수
/// 있지만, 이 구조에서는 빠뜨릴 자리가 없다.
///
/// **이것은 UX 장치다.** 수정된 클라이언트는 이 화면을 지울 수 있고, 그래도
/// 문제가 되면 안 된다 — legacy write 를 실제로 거부하는 것은 Firestore Rules
/// 다. 여기에 보안을 걸지 않는다.
///
/// 첫 판정이 끝날 때까지 앱을 붙잡아두지 않는다. 정책을 읽는 동안 화면을
/// 막으면 오프라인 사용자가 타임아웃만큼 스피너를 보게 되는데, UX 게이트가
/// 실제 사용을 지연시키는 것은 앞뒤가 맞지 않는다.
class AppCompatibilityGate extends StatefulWidget {
  const AppCompatibilityGate({
    super.key,
    required this.child,
    this.service,
    this.onSignOut,
  });

  final Widget child;
  final AppCompatibilityService? service;
  final Future<void> Function()? onSignOut;

  @override
  State<AppCompatibilityGate> createState() => _AppCompatibilityGateState();
}

class _AppCompatibilityGateState extends State<AppCompatibilityGate>
    with WidgetsBindingObserver {
  late final AppCompatibilityService _service =
      widget.service ?? AppCompatibilityService();

  CompatibilityDecision? _decision;
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _evaluate();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 사용자가 스토어에 다녀오면 돌아오는 경로가 resume 이다. 여기서 다시
    // 보지 않으면 업데이트를 마치고도 화면이 그대로 막혀 있다.
    if (state == AppLifecycleState.resumed) {
      _evaluate();
    }
  }

  Future<void> _evaluate() async {
    if (_checking) return;
    setState(() => _checking = true);
    try {
      final decision = await _service.evaluate();
      if (!mounted) return;
      setState(() => _decision = decision);
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final decision = _decision;
    final blocked = decision != null && decision.blocksApp;

    return Stack(
      fit: StackFit.expand,
      children: [
        widget.child,
        if (blocked)
          RequiredUpdateScreen(
            storeUrl: decision.storeUrl,
            onRetry: _evaluate,
            onSignOut: widget.onSignOut,
            isRetrying: _checking,
          ),
      ],
    );
  }
}
