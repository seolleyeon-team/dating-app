import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  String sectionBetween(String source, String startMarker, String endMarker) {
    final start = source.indexOf(startMarker);
    expect(start, isNonNegative, reason: startMarker);
    final end = source.indexOf(endMarker, start + startMarker.length);
    return source.substring(start, end == -1 ? source.length : end);
  }

  test('post write verifies Firebase session before committing', () {
    final source = read(
      'lib/features/community/screens/post_write_screen.dart',
    );
    final submit = sectionBetween(
      source,
      'Future<void> _submitPost()',
      'String _failureMessage',
    );

    final sessionCheck = submit.indexOf('FirebaseAuth.instance.currentUser');
    final createPost = submit.indexOf('provider.createPost');
    final closeScreen = submit.indexOf('Navigator.of(context).pop(true)');

    expect(sessionCheck, isNonNegative);
    expect(createPost, isNonNegative);
    expect(closeScreen, isNonNegative);
    expect(sessionCheck, lessThan(createPost));
    expect(createPost, lessThan(closeScreen));
  });

  test('post write errors are propagated instead of being hidden', () {
    final source = read(
      'lib/features/community/providers/community_provider.dart',
    );
    final create = sectionBetween(
      source,
      'Future<String> createPost',
      'Future<void> refreshAfterPostCreated',
    );

    expect(create, contains('rethrow;'));
  });
}
