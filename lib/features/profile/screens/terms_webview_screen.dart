// =============================================================================
// 이용 약관 WebView 화면
// public/legal/terms.html 을 WebView로 표시
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

class _AppColors {
  static const Color textMain = Color(0xFF181113);
}

class TermsWebViewScreen extends StatefulWidget {
  const TermsWebViewScreen({super.key});

  @override
  State<TermsWebViewScreen> createState() => _TermsWebViewScreenState();
}

class _TermsWebViewScreenState extends State<TermsWebViewScreen> {
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController();
    if (!kIsWeb) {
      _controller.setJavaScriptMode(JavaScriptMode.unrestricted);
    }
    if (kIsWeb) {
      rootBundle.loadString('public/legal/terms.html').then((html) {
        if (mounted) _controller.loadHtmlString(html);
      });
    } else {
      _controller.loadFlutterAsset('public/legal/terms.html');
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: CupertinoColors.systemBackground,
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pop();
          },
          child: const Icon(CupertinoIcons.back, color: _AppColors.textMain),
        ),
        middle: const Text(
          '이용 약관',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: WebViewWidget(controller: _controller),
      ),
    );
  }
}
