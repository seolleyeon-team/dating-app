import 'dart:html' as html;

bool get isInstalledWebApp {
  try {
    return html.window.matchMedia('(display-mode: standalone)').matches ||
        (html.window.navigator as dynamic).standalone == true;
  } catch (_) {
    return false;
  }
}

bool get isIosWebBrowser {
  try {
    final userAgent = html.window.navigator.userAgent.toLowerCase();
    return userAgent.contains('iphone') ||
        userAgent.contains('ipad') ||
        userAgent.contains('ipod');
  } catch (_) {
    return false;
  }
}
