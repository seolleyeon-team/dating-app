import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../router/route_names.dart';
import '../../shared/utils/safe_catch.dart';

/// How long the completion write may stay pending before it is reported.
///
/// A Firestore write made while offline does not fail; its future stays
/// pending until the device is back online. Without a limit the button that
/// ends the tutorial would do nothing, with no message, for as long as that
/// lasts.
const Duration tutorialCompletionTimeout = Duration(seconds: 15);

/// Only one completion runs at a time. The buttons that end the tutorial stay
/// tappable while the write is pending, and every tutorial screen shares this
/// one exit.
bool _completionInFlight = false;

/// Persists the end of the post-onboarding tutorial before entering the app.
///
/// Waiting for the server write is intentional: navigating first lets a user
/// close the app while the completion marker is still missing, which sends
/// them back to the tutorial (or an earlier onboarding step) on restart.
Future<void> completeTutorialAndEnterMain(
  BuildContext context, {
  @visibleForTesting Future<void> Function()? markTutorialSeen,
}) async {
  if (_completionInFlight) return;
  _completionInFlight = true;
  final markSeen =
      markTutorialSeen ?? context.read<AuthProvider>().markTutorialSeen;
  var saved = false;
  try {
    await markSeen().timeout(tutorialCompletionTimeout);
    saved = true;
  } catch (error, stackTrace) {
    logCaughtError('TutorialCompletion', error, stackTrace);
  } finally {
    _completionInFlight = false;
  }
  if (!context.mounted) return;
  if (saved) {
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
    return;
  }
  await showCupertinoDialog<void>(
    context: context,
    builder: (dialogContext) => CupertinoAlertDialog(
      title: const Text('완료 정보를 저장하지 못했어요'),
      content: const Text('네트워크 연결을 확인한 뒤 다시 시도해 주세요.'),
      actions: [
        CupertinoDialogAction(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: const Text('확인'),
        ),
      ],
    ),
  );
}
