// =============================================================================
// 설정 화면
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme, Brightness;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/app_colors.dart';
import '../../../providers/theme_provider.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 메인 화면
// =============================================================================
class SettingsScreen extends StatefulWidget {
  final VoidCallback? onBack;

  const SettingsScreen({super.key, this.onBack});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _profileVisible = true;

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final isDark = themeProvider.isDarkMode;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;
    final textMain = isDark ? AppColorsDark.textPrimary : const Color(0xFF181113);
    final bgColor = isDark ? AppColorsDark.background : const Color(0xFFF8F6F6);
    final surfaceColor = seol.cardSurface;

    return CupertinoPageScaffold(
      backgroundColor: bgColor,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: surfaceColor.withValues(alpha: 0.8),
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            if (widget.onBack != null) {
              widget.onBack!();
            } else {
              Navigator.of(context).pop();
            }
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
            child: Icon(
              CupertinoIcons.back,
              size: 20,
              color: textMain,
            ),
          ),
        ),
        middle: Text(
          '설정',
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
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 48),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SectionTitle(title: '개인정보'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.checkmark_shield,
                        title: '안전도장 로그',
                        subtitle: '만남과 헤어짐 도장 기록 보기',
                        hasChevron: true,
                        onTap: () {
                          HapticFeedback.selectionClick();
                          Navigator.of(
                            context,
                          ).pushNamed(RouteNames.safetyStampLogs);
                        },
                      ),
                      const _Divider(),
                      _SettingsItem(
                        icon: CupertinoIcons.person_badge_minus,
                        title: '연락처 차단',
                        subtitle: '내 연락처의 지인 차단',
                        hasChevron: true,
                        onTap: () {
                          HapticFeedback.selectionClick();
                          Navigator.of(
                            context,
                          ).pushNamed(RouteNames.contactBlock);
                        },
                      ),
                      const _Divider(),
                      _SettingsToggle(
                        icon: CupertinoIcons.eye,
                        title: '프로필 공개',
                        value: _profileVisible,
                        onChanged: (v) => setState(() => _profileVisible = v),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  _SectionTitle(title: '계정'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.person_crop_circle,
                        title: '계정 관리',
                        hasChevron: true,
                        trailing: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: seol.kakao,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Text(
                            '카카오 연동됨',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: seol.kakaoBrown,
                            ),
                          ),
                        ),
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  _SectionTitle(title: '앱 설정'),
                  _SettingsCard(
                    children: [
                      _SettingsToggle(
                        icon: CupertinoIcons.moon,
                        title: '다크 모드',
                        value: themeProvider.isDarkMode,
                        onChanged: (v) => themeProvider.toggleDarkMode(v),
                      ),
                      const _Divider(),
                      _SettingsItem(
                        icon: CupertinoIcons.bell,
                        title: '알림 설정',
                        hasChevron: true,
                        trailing: Text(
                          '켜짐',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color: primary,
                          ),
                        ),
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  _SectionTitle(title: '도움말'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.question_circle,
                        title: '자주 묻는 질문',
                        hasChevron: true,
                        onTap: () {},
                      ),
                      const _Divider(),
                      _SettingsItem(
                        icon: CupertinoIcons.headphones,
                        title: '고객 센터',
                        hasChevron: true,
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  _SectionTitle(title: '의견 보내기'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.chat_bubble,
                        title: '의견 보내기',
                        hasChevron: true,
                        onTap: () {
                          HapticFeedback.selectionClick();
                          Navigator.of(context).pushNamed(RouteNames.inquiry);
                        },
                      ),
                      const _Divider(),
                      _SettingsItem(
                        icon: CupertinoIcons.exclamationmark_triangle,
                        title: '문제 신고',
                        hasChevron: true,
                        onTap: () {
                          HapticFeedback.selectionClick();
                          Navigator.of(
                            context,
                          ).pushNamed(RouteNames.issueReport);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  _SectionTitle(title: '약관'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.doc_text,
                        title: '이용 약관',
                        hasChevron: true,
                        onTap: () {
                          HapticFeedback.selectionClick();
                          Navigator.of(
                            context,
                          ).pushNamed(RouteNames.termsWebview);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  Center(
                    child: Text(
                      '버전 1.0.0',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: seol.gray400,
                      ),
                    ),
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

// =============================================================================
// 섹션 타이틀
// =============================================================================
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

// =============================================================================
// 설정 카드
// =============================================================================
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

// =============================================================================
// 설정 아이템
// =============================================================================
class _SettingsItem extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final bool hasChevron;
  final VoidCallback? onTap;

  const _SettingsItem({
    required this.icon,
    required this.title,
    this.subtitle,
    this.trailing,
    this.hasChevron = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primary = Theme.of(context).colorScheme.primary;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textMain = isDark ? AppColorsDark.textPrimary : const Color(0xFF181113);
    final textSub = isDark ? AppColorsDark.textSecondary : const Color(0xFF89616B);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
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
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        color: textSub,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (trailing != null) ...[trailing!, const SizedBox(width: 8)],
            if (hasChevron)
              Icon(
                CupertinoIcons.chevron_right,
                size: 18,
                color: seol.gray300,
              ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 설정 토글
// =============================================================================
class _SettingsToggle extends StatelessWidget {
  final IconData icon;
  final String title;
  final bool value;
  final ValueChanged<bool> onChanged;

  const _SettingsToggle({
    required this.icon,
    required this.title,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primary = Theme.of(context).colorScheme.primary;
    final textMain = isDark ? AppColorsDark.textPrimary : const Color(0xFF181113);

    return Padding(
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
            child: Text(
              title,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: textMain,
              ),
            ),
          ),
          CupertinoSwitch(
            value: value,
            activeTrackColor: primary,
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 구분선
// =============================================================================
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
