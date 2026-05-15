import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Brightness, Theme;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/app_colors.dart';
import '../../../providers/auth_provider.dart';
import '../../../router/route_names.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

class AccountManagementScreen extends StatefulWidget {
  const AccountManagementScreen({super.key});

  @override
  State<AccountManagementScreen> createState() =>
      _AccountManagementScreenState();
}

class _AccountManagementScreenState extends State<AccountManagementScreen> {
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  bool _isWithdrawing = false;

  Future<void> _withdrawAccount() async {
    if (_isWithdrawing) return;

    final firstConfirm = await showCupertinoDialog<bool>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('계정을 탈퇴하시겠어요?'),
        content: const Text(
          '탈퇴 즉시 프로필이 비공개 처리되고, 추천과 채팅 전송이 중단됩니다. 기존 채팅방에는 상대방 보호를 위해 “탈퇴한 사용자”로 표시됩니다.',
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('탈퇴 진행'),
          ),
        ],
      ),
    );
    if (firstConfirm != true || !mounted) return;

    final finalConfirm = await showCupertinoDialog<bool>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('마지막 확인'),
        content: const Text(
          '탈퇴 후에는 현재 계정으로 서비스를 이용할 수 없습니다. 신고, 제재, 분쟁 대응을 위해 최소 정보는 30일 동안 보관될 수 있습니다.',
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('계정 탈퇴'),
          ),
        ],
      ),
    );
    if (finalConfirm != true || !mounted) return;

    setState(() => _isWithdrawing = true);

    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인 정보를 찾을 수 없습니다.');
      }

      await _userService.withdrawAccount(kakaoUserId: kakaoUserId);
      if (!mounted) return;

      await context.read<AuthProvider>().logout();
      if (!mounted) return;

      Navigator.of(
        context,
        rootNavigator: true,
      ).pushNamedAndRemoveUntil(RouteNames.kakaoAuth, (route) => false);
    } catch (e) {
      if (!mounted) return;
      await showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('탈퇴 처리 실패'),
          content: Text('네트워크 상태를 확인한 뒤 다시 시도해주세요.\n\n$e'),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() => _isWithdrawing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final textSub = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF89616B);
    final bgColor = isDark ? AppColorsDark.background : const Color(0xFFF8F6F6);
    final dangerColor = CupertinoColors.systemRed.resolveFrom(context);

    return CupertinoPageScaffold(
      backgroundColor: bgColor,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: seol.cardSurface.withValues(alpha: 0.8),
        border: null,
        middle: Text(
          '계정 관리',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 48),
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: seol.cardSurface,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(
                      alpha: isDark ? 0.12 : 0.03,
                    ),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '탈퇴 전 꼭 확인해주세요',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                      color: textMain,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '탈퇴하면 프로필은 즉시 비공개 처리되고 추천 목록에서 제외됩니다. 기존 채팅방은 상대방의 대화 기록과 신고 대응을 위해 유지되며, 내 정보는 “탈퇴한 사용자”로 마스킹됩니다.',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      height: 1.45,
                      color: textSub,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '신고, 제재, 분쟁 대응에 필요한 최소 정보는 30일 동안 보관될 수 있습니다.',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 13,
                      height: 1.45,
                      color: textSub,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: _isWithdrawing
                  ? null
                  : () {
                      HapticFeedback.mediumImpact();
                      _withdrawAccount();
                    },
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 18),
                decoration: BoxDecoration(
                  color: dangerColor.withValues(alpha: isDark ? 0.16 : 0.08),
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Center(
                  child: _isWithdrawing
                      ? CupertinoActivityIndicator(color: dangerColor)
                      : Text(
                          '계정 탈퇴',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: dangerColor,
                          ),
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
