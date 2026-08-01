const fs = require('fs');
const path = 'test/widget_test.dart';
const before = fs.readFileSync(path, 'utf8').replace(/^\uFEFF/, '');
const oldText = `      const SeolleyeonApp(\n        testHome: Scaffold(body: Center(child: Text('설레연'))),\n      ),\n    );\n\n    expect(find.text('설레연'), findsOneWidget);`;
const newText = `      const SeolleyeonApp(\n        testHome: Scaffold(body: SizedBox(key: Key('app-test-home'))),\n      ),\n    );\n\n    expect(find.byKey(const Key('app-test-home')), findsOneWidget);`;
if (!before.includes(oldText)) throw new Error('widget test block not found');
fs.writeFileSync(path, before.replace(oldText, newText));
