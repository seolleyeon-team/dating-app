import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../router/route_names.dart';

/// Persists the end of the post-onboarding tutorial before entering the app.
///
/// Waiting for the server write is intentional: navigating first lets a user
/// close the app while the completion marker is still missing, which sends
/// them back to the tutorial (or an earlier onboarding step) on restart.
Future<void> completeTutorialAndEnterMain(BuildContext context) async {
  try {
    await context.read<AuthProvider>().markTutorialSeen();
    if (!context.mounted) return;
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
  } catch (_) {
    if (!context.mounted) return;
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
}
