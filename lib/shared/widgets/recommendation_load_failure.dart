import 'package:flutter/cupertino.dart';

/// Generic retryable failure state for the 1:1 recommendation surfaces.
///
/// (The former KakaoRecommendationPrivacyPrerequisite consent-gate widget is
/// gone with the one-time-snapshot architecture: the friend snapshot happens
/// at the setup ladder's connection gate, so the feed no longer renders a
/// consent prerequisite.)
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
