import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/app_colors.dart';
import '../../shared/widgets/buttons/primary_button.dart';
import '../../shared/widgets/buttons/secondary_button.dart';

/// 업데이트가 필요할 때 본 화면 위에 덮이는 화면.
///
/// 사용자에게 보안 사정을 설명하지 않는다. "최신 버전이 필요하다" 로 충분하고
/// 공포성 문구는 도움이 되지 않는다.
class RequiredUpdateScreen extends StatelessWidget {
  const RequiredUpdateScreen({
    super.key,
    required this.storeUrl,
    required this.onRetry,
    this.onSignOut,
    this.isRetrying = false,
  });

  final String? storeUrl;

  /// 네트워크가 잠깐 끊겼을 뿐인 경우와 정말 구버전인 경우를 사용자가
  /// 구분할 수 있게, 스토어로 보내기만 하지 않고 재확인 수단을 준다.
  final Future<void> Function() onRetry;

  /// 공용 기기에서 계정을 두고 나가야 하는 경우가 있다. 앱 내부로 들어가지
  /// 않는 조작이라 막을 이유가 없다.
  final Future<void> Function()? onSignOut;

  final bool isRetrying;

  Future<void> _openStore() async {
    final url = storeUrl;
    if (url == null) return;
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    // 이 화면은 라우트가 아니라 Navigator 위에 겹쳐진다. 그래서 뒤로가기로
    // 벗어날 대상이 없다 — 아래에서 라우트가 pop 되어도 이 화면은 남는다.
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(
                  Icons.system_update,
                  size: 64,
                  color: AppColors.primary,
                ),
                const SizedBox(height: 24),
                Text(
                  '업데이트가 필요해요',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '설레연을 계속 이용하려면 최신 버전으로 업데이트해 주세요.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: AppColors.textSecondary,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 32),
                if (storeUrl != null)
                  PrimaryButton(text: '업데이트하기', onPressed: _openStore)
                else
                  // 스토어 주소를 모르면 버튼을 띄우지 않는다. 눌러도 아무 일도
                  // 일어나지 않는 버튼은 사용자를 더 헤매게 만든다.
                  Text(
                    '스토어에서 설레연을 검색해 업데이트해 주세요.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                const SizedBox(height: 12),
                SecondaryButton(
                  text: '다시 확인',
                  isLoading: isRetrying,
                  onPressed: isRetrying ? null : () => onRetry(),
                ),
                if (onSignOut != null) ...[
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: () => onSignOut!(),
                    child: const Text(
                      '로그아웃',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
