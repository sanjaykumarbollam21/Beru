import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:beru_mobile/main.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('BeruApp renders title and hub settings', (WidgetTester tester) async {
    await tester.pumpWidget(const BeruApp());
    await tester.pumpAndSettle();
    expect(find.text('Beru Assistant (Phase 1)'), findsOneWidget);
    expect(find.text('Hub Connection Settings'), findsOneWidget);
    expect(find.text('Device Registration / Pairing'), findsOneWidget);
  });
}
