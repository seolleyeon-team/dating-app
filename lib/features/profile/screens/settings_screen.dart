// =============================================================================
// 설정 화면
// 경로: lib/features/settings/screens/settings_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const SettingsScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF89616B);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color kakao = Color(0xFFFEE500);
  static const Color kakaoBrown = Color(0xFF3C1E1E);
}

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
  bool _darkMode = false;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.surfaceLight.withValues(alpha: 0.8),
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
              color: CupertinoColors.black.withValues(alpha: 0.05),
            ),
            child: const Icon(
              CupertinoIcons.back,
              size: 20,
              color: _AppColors.textMain,
            ),
          ),
        ),
        middle: const Text(
          '설정',
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: Stack(
        children: [
          // 배경 글로우
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
                      _AppColors.primary.withValues(alpha: 0.06),
                      _AppColors.primary.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 48),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 개인정보
                  _SectionTitle(title: '개인정보'),
                  _SettingsCard(
                    children: [
                      _SettingsItem(
                        icon: CupertinoIcons.person_badge_minus,
                        title: '연락처 차단',
                        subtitle: '내 연락처의 지인 차단',
                        hasChevron: true,
                        onTap: () {},
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
                  // 계정
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
                            color: _AppColors.kakao,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            '카카오 연동됨',
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.kakaoBrown,
                            ),
                          ),
                        ),
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  // 앱 설정
                  _SectionTitle(title: '앱 설정'),
                  _SettingsCard(
                    children: [
                      _SettingsToggle(
                        icon: CupertinoIcons.moon,
                        title: '다크 모드',
                        value: _darkMode,
                        onChanged: (v) => setState(() => _darkMode = v),
                      ),
                      const _Divider(),
                      _SettingsItem(
                        icon: CupertinoIcons.bell,
                        title: '알림 설정',
                        hasChevron: true,
                        trailing: const Text(
                          '켜짐',
                          style: TextStyle(
                            fontFamily: 'Noto Sans KR',
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.primary,
                          ),
                        ),
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  // 도움말
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
                  // 의견 보내기
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
                  // 약관
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
                  // 버전
                  const Center(
                    child: Text(
                      '버전 1.0.0',
                      style: TextStyle(
                        fontFamily: 'Noto Sans KR',
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.gray400,
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
    return Padding(
      padding: const EdgeInsets.only(left: 16, bottom: 12),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          fontFamily: 'Noto Sans KR',
          fontSize: 12,
          fontWeight: FontWeight.w700,
          letterSpacing: 1,
          color: _AppColors.gray400,
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
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(32),
        border: Border.all(
          color: _AppColors.surfaceLight.withValues(alpha: 0.5),
        ),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
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
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            // 아이콘
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _AppColors.primary.withValues(alpha: 0.05),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 22, color: _AppColors.primary),
            ),
            const SizedBox(width: 16),
            // 텍스트
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textMain,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      style: const TextStyle(
                        fontFamily: 'Noto Sans KR',
                        fontSize: 13,
                        color: _AppColors.textSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            // 트레일링
            if (trailing != null) ...[trailing!, const SizedBox(width: 8)],
            if (hasChevron)
              const Icon(
                CupertinoIcons.chevron_right,
                size: 18,
                color: _AppColors.gray300,
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
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          // 아이콘
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.05),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, size: 22, color: _AppColors.primary),
          ),
          const SizedBox(width: 16),
          // 타이틀
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontFamily: 'Noto Sans KR',
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: _AppColors.textMain,
              ),
            ),
          ),
          // 토글
          CupertinoSwitch(
            value: value,
            activeTrackColor: _AppColors.primary,
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
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20),
      height: 1,
      color: _AppColors.gray100,
    );
  }
}
