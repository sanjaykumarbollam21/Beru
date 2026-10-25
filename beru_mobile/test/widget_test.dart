import 'package:flutter_test/flutter_test.dart';
import 'package:beru_mobile/main.dart';

void main() {
  testWidgets('BeruApp renders title and idle state', (WidgetTester tester) async {
    await tester.pumpWidget(const BeruApp());
    expect(find.text('Beru Assistant'), findsOneWidget);
    expect(find.text('Idle'), findsOneWidget);
  });
}
