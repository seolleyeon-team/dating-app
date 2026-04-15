import 'package:flutter/cupertino.dart';

import '../../../services/storage_service.dart';
import '../models/safety_stamp_follow_up_args.dart';
import '../services/safety_stamp_follow_up_service.dart';

class _AppColors {
  static const Color primary = Color(0xFFFF5A7E);
  static const Color textMain = Color(0xFF111111);
  static const Color textSub = Color(0xFF6B7280);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color surface = CupertinoColors.white;
}

class SafetyStampFollowUpScreen extends StatefulWidget {
  final SafetyStampFollowUpArgs args;

  const SafetyStampFollowUpScreen({super.key, required this.args});

  @override
  State<SafetyStampFollowUpScreen> createState() =>
      _SafetyStampFollowUpScreenState();
}

class _SafetyStampFollowUpScreenState extends State<SafetyStampFollowUpScreen> {
  final StorageService _storageService = StorageService();
  final SafetyStampFollowUpService _followUpService =
      SafetyStampFollowUpService();
  final TextEditingController _otherReasonController = TextEditingController();

  String? _currentUserId;
  SafetyStampFollowUpReason? _selectedReason;
  bool _isLoading = true;
  bool _isSubmitting = false;
  bool _hasSubmitted = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _otherReasonController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (widget.args.roomId.isEmpty || widget.args.promiseId.isEmpty) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
      return;
    }

    final userId = await _storageService.getKakaoUserId();
    if (userId == null || userId.isEmpty) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
      return;
    }

    final draft = await _followUpService.loadDraft(
      roomId: widget.args.roomId,
      promiseId: widget.args.promiseId,
      userId: userId,
    );

    if (!mounted) return;
    _otherReasonController.text = draft.otherText;
    setState(() {
      _currentUserId = userId;
      _selectedReason = draft.reason;
      _hasSubmitted = draft.hasSubmitted;
      _isLoading = false;
    });
  }

  Future<void> _submit() async {
    final userId = _currentUserId;
    final reason = _selectedReason;
    if (userId == null || userId.isEmpty || reason == null) return;

    if (reason == SafetyStampFollowUpReason.other &&
        _otherReasonController.text.trim().isEmpty) {
      await _showAlert('기타 사유를 입력해주세요.');
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    try {
      await _followUpService.submitReason(
        roomId: widget.args.roomId,
        promiseId: widget.args.promiseId,
        userId: userId,
        reason: reason,
        otherText: _otherReasonController.text,
        notificationId: widget.args.notificationId,
      );

      if (!mounted) return;
      setState(() {
        _hasSubmitted = true;
      });
      await _showAlert('사유가 저장되었어요.');
      if (!mounted) return;
      Navigator.of(context).maybePop();
    } catch (_) {
      await _showAlert('사유를 저장하지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  Future<void> _showAlert(String message) {
    return showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('안내'),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  Widget _buildReasonTile(
    SafetyStampFollowUpReason reason,
    String title,
    String subtitle,
  ) {
    final isSelected = _selectedReason == reason;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        setState(() {
          _selectedReason = reason;
        });
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: _AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: isSelected ? _AppColors.primary : _AppColors.gray200,
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              isSelected
                  ? CupertinoIcons.check_mark_circled_solid
                  : CupertinoIcons.circle,
              color: isSelected ? _AppColors.primary : _AppColors.textSub,
              size: 22,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 13,
                      height: 1.4,
                      color: _AppColors.textSub,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const CupertinoPageScaffold(
        child: Center(child: CupertinoActivityIndicator()),
      );
    }

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        middle: const Text(
          '헤어짐 도장 확인',
          style: TextStyle(fontFamily: 'Pretendard'),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).maybePop(),
          child: const Icon(CupertinoIcons.back),
        ),
      ),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
          children: [
            if (_currentUserId == null || _currentUserId!.isEmpty)
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  '로그인 정보를 확인할 수 없어 사유를 저장할 수 없어요.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    color: _AppColors.textSub,
                  ),
                ),
              )
            else
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '헤어짐 도장을 찍지 않으셨네요. 무슨 일이 있으셨나요?',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: _AppColors.textMain,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      '약속은 자동으로 완료 처리되었어요. 이유를 남겨주시면 이후 기록과 안내 품질을 개선하는 데 도움이 돼요.',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        height: 1.5,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 20),
            _buildReasonTile(
              SafetyStampFollowUpReason.phoneOff,
              '약속 중에 폰이 꺼졌어요',
              '배터리 방전이나 전원 문제로 헤어짐 도장을 누르지 못했어요.',
            ),
            const SizedBox(height: 12),
            _buildReasonTile(
              SafetyStampFollowUpReason.forgotToStamp,
              '헤어짐 도장 누르는 것을 깜빡했어요',
              '약속은 끝났지만 도장을 누르는 걸 놓쳤어요.',
            ),
            const SizedBox(height: 12),
            _buildReasonTile(
              SafetyStampFollowUpReason.other,
              '기타 사유',
              '다른 이유가 있다면 직접 입력해주세요.',
            ),
            if (_selectedReason == SafetyStampFollowUpReason.other) ...[
              const SizedBox(height: 12),
              CupertinoTextField(
                controller: _otherReasonController,
                maxLines: 4,
                minLines: 4,
                padding: const EdgeInsets.all(14),
                placeholder: '사유를 입력해주세요',
                style: const TextStyle(fontFamily: 'Pretendard', fontSize: 14),
                decoration: BoxDecoration(
                  color: _AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: _AppColors.gray200),
                ),
              ),
            ],
            const SizedBox(height: 24),
            CupertinoButton(
              color: _AppColors.primary,
              borderRadius: BorderRadius.circular(16),
              onPressed: _isSubmitting || _currentUserId == null
                  ? null
                  : _submit,
              child: _isSubmitting
                  ? const CupertinoActivityIndicator(
                      color: CupertinoColors.white,
                    )
                  : Text(
                      _hasSubmitted ? '다시 저장하기' : '사유 저장하기',
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
