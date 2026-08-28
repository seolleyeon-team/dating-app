import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/widgets/seolleyeon_splash_view.dart';

void main() {
  testWidgets('splash title has no underline', (tester) async {
    await tester.pumpWidget(const CupertinoApp(home: SeolleyeonSplashView()));

    final title = tester.widget<Text>(find.text('설레연'));

    expect(title.style?.decoration, TextDecoration.none);
    expect(title.style?.fontFamily, 'NanumSquareRound');
    expect(title.style?.color, SeolleyeonSplashView.accentColor);
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
  });
}
