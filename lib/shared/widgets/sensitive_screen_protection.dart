import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import '../../services/screen_security_service.dart';

class SensitiveScreenProtection extends StatefulWidget {
  final Widget child;

  const SensitiveScreenProtection({super.key, required this.child});

  @override
  State<SensitiveScreenProtection> createState() =>
      _SensitiveScreenProtectionState();
}

class _SensitiveScreenProtectionState extends State<SensitiveScreenProtection> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || kIsWeb) return;
      ScreenSecurityService.instance.enterSensitiveScreen();
    });
  }

  @override
  void dispose() {
    if (!kIsWeb) {
      ScreenSecurityService.instance.exitSensitiveScreen();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
