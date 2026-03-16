/// 웹 플랫폼에서 WebViewPlatform 등록
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';
import 'package:webview_flutter_web/webview_flutter_web.dart';

void registerWebViewWebPlatform() {
  WebViewPlatform.instance = WebWebViewPlatform();
}
