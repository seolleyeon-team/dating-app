// =============================================================================
// 알림 설정 화면
// =============================================================================

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show Brightness, Theme;
import 'package:flutter/services.dart';

import '../../../core/constants/app_colors.dart';
import '../../../services/push_notification_service.dart';
import '../../../services/storage_service.dart';

class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends State<NotificationSettingsScreen> {
  final PushNotificationService _pushService = PushNotificationService.instance;
  final StorageService _storageService = StorageService();

  Map<String, bool> _settings = Map<String, bool>.from(
    PushNotificationService.defaultNotificationSettings,
  );
  AuthorizationStatus? _systemStatus;
  bool _isLoading = true;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      final userSettings = await _pushService.loadUserNotificationSettings(
        userId: kakaoUserId,
      );
      final systemSettings = await _pushService.getSystemNotificationSettings();
      if (!mounted) return;
      setState(() {
        _settings = userSettings;
        _systemStatus = systemSettings.authorizationStatus;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      await _showAlert('불러오기 실패', '알림 설정을 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
    }
  }

  Future<void> _toggleAll(bool value) async {
    if (_isSaving) return;
    HapticFeedback.selectionClick();

    if (value) {
      final systemSettings = await _pushService.requestSystemPermission();
      if (!mounted) return;
      setState(() => _systemStatus = systemSettings.authorizationStatus);

      if (!_isSystemNotificationAllowed(systemSettings.authorizationStatus)) {
        await _showPermissionGuide();
        return;
      }
    }

    final next = Map<String, bool>.from(_settings)..['all'] = value;
    await _saveSettings(next);
  }

  Future<void> _toggleCategory(String key, bool value) async {
    if (_isSaving || _settings['all'] == false) return;
    HapticFeedback.selectionClick();

    final next = Map<String, bool>.from(_settings)..[key] = value;
    await _saveSettings(next);
  }

  Future<void> _saveSettings(Map<String, bool> next) async {
    final previous = Map<String, bool>.from(_settings);
    setState(() {
      _settings = next;
      _isSaving = true;
    });

    try {
      final kakaoUserId = await _storageService.getKakaoUserId();
      await _pushService.saveUserNotificationSettings(
        userId: kakaoUserId,
        settings: next,
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _settings = previous);
      await _showAlert('저장 실패', '알림 설정을 저장하지 못했어요. 네트워크 상태를 확인해주세요.');
    } finally {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  bool _isSystemNotificationAllowed(AuthorizationStatus? status) {
    return status == AuthorizationStatus.authorized ||
        status == AuthorizationStatus.provisional;
  }

  String _systemPermissionLabel() {
    switch (_systemStatus) {
      case AuthorizationStatus.authorized:
        return '시스템 권한 허용됨';
      case AuthorizationStatus.provisional:
        return '시스템 권한 임시 허용됨';
      case AuthorizationStatus.denied:
        return '시스템 권한 꺼짐';
      case AuthorizationStatus.notDetermined:
        return '시스템 권한 미설정';
      default:
        return '시스템 권한 확인 중';
    }
  }

  String _platformGuideText() {
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      return 'iPhone 설정 > 알림 > 설레연에서 알림 허용을 켜야 실제 푸시가 표시돼요.';
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'Android 설정 > 앱 > 설레연 > 알림에서 알림 허용을 켜야 실제 푸시가 표시돼요.';
    }
    return '기기 설정에서 설레연 알림 권한이 켜져 있어야 실제 푸시가 표시돼요.';
  }

  Future<void> _showPermissionGuide() async {
    await _showAlert('기기 알림 권한이 꺼져 있어요', _platformGuideText());
  }

  Future<void> _showAlert(String title, String message) async {
    if (!mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final bgColor = isDark ? AppColorsDark.background : const Color(0xFFF8F6F6);
    final surfaceColor = seol.cardSurface;
    final allEnabled = _settings['all'] != false;
    final permissionAllowed = _isSystemNotificationAllowed(_systemStatus);

    return CupertinoPageScaffold(
      backgroundColor: bgColor,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: surfaceColor.withValues(alpha: 0.8),
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pop();
          },
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDark
                  ? CupertinoColors.white.withValues(alpha: 0.08)
                  : CupertinoColors.black.withValues(alpha: 0.05),
            ),
            child: Icon(CupertinoIcons.back, size: 20, color: textMain),
          ),
        ),
        middle: Text(
          '알림 설정',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: textMain,
          ),
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            top: -100,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: MediaQuery.of(context).size.width * 1.4,
                height: MediaQuery.of(context).size.height * 0.5,
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    colors: [
                      primary.withValues(alpha: isDark ? 0.04 : 0.06),
                      primary.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            child: _isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 48),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _InfoCard(
                          icon: permissionAllowed
                              ? CupertinoIcons.bell_fill
                              : CupertinoIcons.bell_slash,
                          title: _systemPermissionLabel(),
                          body: permissionAllowed
                              ? '아래 항목별 설정에 따라 설레연 푸시 알림을 받을 수 있어요.'
                              : _platformGuideText(),
                        ),
                        const SizedBox(height: 28),
                        const _SectionTitle(title: '전체'),
                        _SettingsCard(
                          children: [
                            _NotificationToggle(
                              icon: CupertinoIcons.bell,
                              title: '전체 알림',
                              subtitle: '채팅, 매칭, 커뮤니티 등 모든 푸시 알림',
                              value: allEnabled,
                              isSaving: _isSaving,
                              onChanged: _toggleAll,
                            ),
                          ],
                        ),
                        const SizedBox(height: 28),
                        const _SectionTitle(title: '알림 종류'),
                        _SettingsCard(
                          children: [
                            _NotificationToggle(
                              icon: CupertinoIcons.chat_bubble_2,
                              title: '채팅 알림',
                              subtitle: '1:1 채팅과 읽지 않은 채팅 요약',
                              value: _settings['chat'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('chat', value),
                            ),
                            const _Divider(),
                            _NotificationToggle(
                              icon: CupertinoIcons.heart,
                              title: '매칭/좋아요 알림',
                              subtitle: '프로필 좋아요와 매칭 관련 알림',
                              value: _settings['matching'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('matching', value),
                            ),
                            const _Divider(),
                            _NotificationToggle(
                              icon: CupertinoIcons.tree,
                              title: '대나무숲 알림',
                              subtitle: '댓글, 답글, 게시글 좋아요',
                              value: _settings['community'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('community', value),
                            ),
                            const _Divider(),
                            _NotificationToggle(
                              icon: CupertinoIcons.question_circle,
                              title: '무물 알림',
                              subtitle: '새 질문이 도착했을 때',
                              value: _settings['asks'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('asks', value),
                            ),
                            const _Divider(),
                            _NotificationToggle(
                              icon: CupertinoIcons.calendar,
                              title: '이벤트 알림',
                              subtitle: '3:3 초대와 이벤트 진행 알림',
                              value: _settings['events'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('events', value),
                            ),
                            const _Divider(),
                            _NotificationToggle(
                              icon: CupertinoIcons.checkmark_shield,
                              title: '안전도장 알림',
                              subtitle: '약속 후 안전 확인 리마인드',
                              value: _settings['safety'] != false,
                              enabled: allEnabled,
                              isSaving: _isSaving,
                              onChanged: (value) =>
                                  _toggleCategory('safety', value),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;

  const _InfoCard({
    required this.icon,
    required this.title,
    required this.body,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primary = Theme.of(context).colorScheme.primary;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final textSub = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF89616B);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
          color: isDark
              ? seol.gray200.withValues(alpha: 0.3)
              : seol.cardSurface.withValues(alpha: 0.5),
        ),
        boxShadow: [
          BoxShadow(
            color: isDark
                ? CupertinoColors.black.withValues(alpha: 0.12)
                : CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: primary.withValues(alpha: isDark ? 0.12 : 0.06),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: primary, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: textMain,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  body,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    height: 1.4,
                    color: textSub,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;

  const _SectionTitle({required this.title});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    return Padding(
      padding: const EdgeInsets.only(left: 16, bottom: 12),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 12,
          fontWeight: FontWeight.w700,
          letterSpacing: 1,
          color: seol.gray400,
        ),
      ),
    );
  }
}

class _SettingsCard extends StatelessWidget {
  final List<Widget> children;

  const _SettingsCard({required this.children});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(32),
        border: Border.all(
          color: isDark
              ? seol.gray200.withValues(alpha: 0.3)
              : seol.cardSurface.withValues(alpha: 0.5),
        ),
        boxShadow: [
          BoxShadow(
            color: isDark
                ? CupertinoColors.black.withValues(alpha: 0.12)
                : CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(children: children),
    );
  }
}

class _NotificationToggle extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool value;
  final bool enabled;
  final bool isSaving;
  final ValueChanged<bool> onChanged;

  const _NotificationToggle({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    this.enabled = true,
    required this.isSaving,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primary = Theme.of(context).colorScheme.primary;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final textSub = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF89616B);
    final active = enabled && !isSaving;

    return Opacity(
      opacity: enabled ? 1 : 0.45,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: primary.withValues(alpha: isDark ? 0.12 : 0.05),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 22, color: primary),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      color: textMain,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 13,
                      color: textSub,
                    ),
                  ),
                ],
              ),
            ),
            CupertinoSwitch(
              value: value,
              activeTrackColor: primary,
              onChanged: active ? onChanged : null,
            ),
          ],
        ),
      ),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20),
      height: 1,
      color: seol.gray100,
    );
  }
}
