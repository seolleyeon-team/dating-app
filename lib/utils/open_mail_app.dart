import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

const _channel = MethodChannel('com.yonsei.dating/open_mail_app');

Future<void> openGmailApp(BuildContext context) async {
  // Android: 네이티브 getLaunchIntentForPackage로 Gmail 앱 직접 실행
  if (Platform.isAndroid) {
    try {
      final launched = await _channel.invokeMethod<bool>('launchGmail');
      if (launched == true) return;
    } catch (_) {}
    // 네이티브 실패 시 intent URL 시도
    try {
      final uri = Uri.parse(
        'intent://#Intent;package=com.google.android.gm;action=android.intent.action.MAIN;category=android.intent.category.LAUNCHER;end',
      );
      if (await launchUrl(uri, mode: LaunchMode.externalApplication)) return;
    } catch (_) {}
  }

  // iOS: googlegmail 스킴 (LSApplicationQueriesSchemes에 googlegmail 추가됨)
  if (Platform.isIOS) {
    final iosUris = [
      Uri.parse('googlegmail:///inbox'),
      Uri.parse('googlegmail://'),
    ];
    for (final uri in iosUris) {
      try {
        if (await launchUrl(uri, mode: LaunchMode.externalApplication)) return;
      } catch (_) {}
    }
  }

  // 앱 실행 실패 시 안내 (웹 열지 않음 - workspace 리다이렉트 방지)
  if (context.mounted) {
    await showCupertinoDialog<void>(
      context: context,
      builder: (_) => const CupertinoAlertDialog(
        title: Text('메일 앱을 열 수 없음'),
        content: Text(
          'Gmail 앱이 설치되어 있는지 확인해주세요.\n설치 후 앱을 직접 열어주세요.',
        ),
        actions: [
          CupertinoDialogAction(child: Text('확인')),
        ],
      ),
    );
  }
}
