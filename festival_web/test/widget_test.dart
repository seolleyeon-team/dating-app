import 'package:festival_web/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows festival access screen', (tester) async {
    await tester.pumpWidget(const FestivalWebApp());

    expect(find.text('축제에서 만나는\n오늘의 인연'), findsOneWidget);
    expect(find.text('입장하기'), findsOneWidget);
  });
}
