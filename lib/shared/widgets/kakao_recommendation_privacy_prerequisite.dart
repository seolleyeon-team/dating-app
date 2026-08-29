import 'package:flutter/cupertino.dart';

/// Fail-closed recovery UI for users whose Kakao friend-list reconciliation
/// has not completed. The caller owns the consent/sync action so this widget
/// stays reusable across every 1:1 recommendation surface.
class KakaoRecommendationPrivacyPrerequisite extends StatelessWidget {
  final bool isWorking;
  final String? errorMessage;
  final Future<void> Function() onConsentAndSync;

  const KakaoRecommendationPrivacyPrerequisite({
    super.key,
    required this.isWorking,
    required this.onConsentAndSync,
    this.errorMessage,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                CupertinoIcons.person_2_fill,
                size: 42,
                color: Color(0xFF7C3AED),
              ),
              const SizedBox(height: 16),
              const Text(
                '카카오 친구목록 동의가 필요해요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF111827),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '이 앱을 사용하는 카카오톡 친구가 친구 피하기를 설정한 경우, 서로 추천되지 않도록 확인하기 위해 사용해요. 동기화가 끝나기 전에는 1:1 추천을 보여드리지 않아요.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  height: 1.45,
                  color: Color(0xFF6B7280),
                ),
              ),
              if (errorMessage != null) ...[
                const SizedBox(height: 12),
                Text(
                  errorMessage!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    color: Color(0xFFDC2626),
                  ),
                ),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton.filled(
                  onPressed: isWorking ? null : onConsentAndSync,
                  child: isWorking
                      ? const CupertinoActivityIndicator(
                          color: CupertinoColors.white,
                        )
                      : const Text('동의하고 추천 시작하기'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RecommendationLoadFailure extends StatelessWidget {
  final Future<void> Function() onRetry;

  const RecommendationLoadFailure({super.key, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              '추천 정보를 불러오지 못했어요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 17,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '인터넷 연결을 확인하고 다시 시도해 주세요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                color: Color(0xFF6B7280),
              ),
            ),
            const SizedBox(height: 18),
            CupertinoButton(onPressed: onRetry, child: const Text('다시 시도')),
          ],
        ),
      ),
    );
  }
}
