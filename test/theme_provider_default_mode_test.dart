import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/providers/theme_provider.dart';

void main() {
  test('다크 모드를 켜기 전에는 라이트 테마가 기본값이다', () {
    final provider = ThemeProvider();

    expect(provider.themeMode, ThemeMode.light);
    expect(provider.isDarkMode, isFalse);
  });
}
