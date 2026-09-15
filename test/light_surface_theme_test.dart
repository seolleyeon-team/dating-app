import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/widgets/light_surface_theme.dart';

void main() {
  testWidgets('uses dark text on a white flow under global dark mode', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: const LightSurfaceTheme(child: Scaffold(body: TextField())),
      ),
    );

    final fieldContext = tester.element(find.byType(TextField));
    final theme = Theme.of(fieldContext);

    expect(theme.brightness, Brightness.light);
    expect(theme.colorScheme.surface, const Color(0xFFFFFFFF));
    expect(theme.colorScheme.onSurface, const Color(0xFF0F172A));
  });
}
