import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme;

import '../services/recommendation_refresh_service.dart';

/// 1대1 추천 새로고침 결제 확인 다이얼로그.
///
/// "새로고침 하기" CTA 는 결제 요청이 진행 중이면 비활성화되어 중복 탭을
/// 막는다 (서버 idempotency 가 최종 방어선이고, 이건 UX 보호막이다).
/// 결과는 [RecommendationRefreshPurchaseResult] 로 pop 되며, 결제 실패
/// 예외는 그대로 pop 없이 호출자에게 전달하지 않고 null 로 닫은 뒤
/// 호출자가 에러 안내를 표시한다.
class RecommendationRefreshDialog extends StatefulWidget {
  const RecommendationRefreshDialog({super.key, required this.onPurchase});

  /// 서버 결제 요청. 성공/실패 판정은 서버 응답만 신뢰한다.
  final Future<RecommendationRefreshPurchaseResult> Function() onPurchase;

  final int priceHearts = RecommendationRefreshService.costHearts;

  @override
  State<RecommendationRefreshDialog> createState() =>
      _RecommendationRefreshDialogState();
}

class _RecommendationRefreshDialogState
    extends State<RecommendationRefreshDialog> {
  bool _isSubmitting = false;
  bool _submitFailed = false;

  Future<void> _submit() async {
    if (_isSubmitting) return;
    setState(() {
      _isSubmitting = true;
      _submitFailed = false;
    });
    try {
      final result = await widget.onPurchase();
      if (!mounted) return;
      Navigator.of(context).pop(result);
    } catch (_) {
      // 네트워크/세션 오류. Heart 는 서버 트랜잭션이 지키므로 여기서는
      // 화면 상태만 원복하고 재시도를 허용한다.
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _submitFailed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoAlertDialog(
      title: const Padding(
        padding: EdgeInsets.only(bottom: 4),
        child: Text('정말로 새로고침 하시겠습니까?'),
      ),
      content: Text(
        _submitFailed
            ? '새로고침을 완료하지 못했어요. 잠시 후 다시 시도해주세요.'
            : '오늘의 추천 3명을 다음 순위 3명으로 바꿔드려요.\n하루 추천마다 1번만 새로고침할 수 있어요.',
      ),
      actions: [
        CupertinoDialogAction(
          onPressed: _isSubmitting ? null : () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        CupertinoDialogAction(
          key: const Key('one_to_one_refresh_confirm_button'),
          isDefaultAction: true,
          onPressed: _isSubmitting ? null : _submit,
          child: _isSubmitting
              ? const CupertinoActivityIndicator()
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('새로고침 하기'),
                    const SizedBox(width: 6),
                    Icon(
                      CupertinoIcons.heart_fill,
                      size: 15,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(width: 2),
                    Text('${widget.priceHearts} 하트'),
                  ],
                ),
        ),
      ],
    );
  }
}
