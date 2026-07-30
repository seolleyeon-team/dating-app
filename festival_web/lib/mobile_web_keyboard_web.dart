// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter

import 'dart:html' as html;

import 'package:flutter/foundation.dart';

ValueNotifier<double>? _notifier;
var _listening = false;

ValueNotifier<double> createMobileWebKeyboardInsetNotifier() {
  _notifier ??= ValueNotifier<double>(0);
  if (!_listening) {
    _listening = true;
    _attachVisualViewportListener();
  }
  return _notifier!;
}

void _attachVisualViewportListener() {
  final visualViewport = html.window.visualViewport;
  if (visualViewport == null) return;

  void sync() {
    final layoutHeight = html.window.innerHeight?.toDouble() ?? 0;
    final visibleHeight = visualViewport.height ?? layoutHeight;
    final offsetTop = visualViewport.offsetTop ?? 0;
    final inset = layoutHeight - visibleHeight - offsetTop;
    final next = inset.isNegative ? 0.0 : inset;
    final notifier = _notifier;
    if (notifier != null && notifier.value != next) {
      notifier.value = next;
    }
  }

  visualViewport.onResize.listen((_) => sync());
  visualViewport.onScroll.listen((_) => sync());
  html.window.onResize.listen((_) => sync());
  sync();
}
