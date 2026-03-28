// =============================================================================
// 약관 동의 화면
// 경로: lib/features/auth/screens/terms_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/auth/screens/terms_screen.dart';
// ...
// home: const TermsScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';
import 'terms_detail_sheet.dart';
import '../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0537A);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1B0D11);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color textMuted = Color(0xFF9CA3AF);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
}

// =============================================================================
// 약관 항목 데이터 모델
// =============================================================================
class TermsItem {
  final String id;
  final String label;
  final bool isRequired;
  final bool hasDetail;
  bool isChecked;

  TermsItem({
    required this.id,
    required this.label,
    required this.isRequired,
    this.hasDetail = false,
    this.isChecked = false,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class TermsScreen extends StatefulWidget {
  const TermsScreen({super.key});

  @override
  State<TermsScreen> createState() => _TermsScreenState();
}

class _TermsScreenState extends State<TermsScreen> {
  final List<TermsItem> _requiredTerms = [
    TermsItem(id: 'age', label: '만 19세 이상입니다', isRequired: true),
    TermsItem(
      id: 'service',
      label: '서비스 이용약관 동의',
      isRequired: true,
      hasDetail: true,
    ),
    TermsItem(
      id: 'privacy',
      label: '개인정보 수집 및 이용 동의',
      isRequired: true,
      hasDetail: true,
    ),
  ];

  bool _marketingChecked = false;
  bool _pushEnabled = false;
  bool _emailEnabled = false;

  bool get _allRequiredChecked =>
      _requiredTerms.every((item) => item.isChecked);

  bool get _allChecked => _allRequiredChecked && _marketingChecked;

  Future<void> _enterWithTestAccount() async {
    final storage = StorageService();
    await storage.saveKakaoUserId("fake_user_1");

    if (!mounted) return;

    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
  }

  void _toggleAll(bool value) {
    setState(() {
      for (var item in _requiredTerms) {
        item.isChecked = value;
      }
      _marketingChecked = value;
      if (value) {
        _pushEnabled = true;
        _emailEnabled = true;
      }
    });
    HapticFeedback.selectionClick();
  }

  void _toggleItem(TermsItem item, bool value) {
    setState(() {
      item.isChecked = value;
    });
    HapticFeedback.selectionClick();
  }

  void _onDetailPressed(TermsItem item) {
    HapticFeedback.lightImpact();
    TermsDetailSheet.show(
      context,
      title: item.label,
      sections: const [
        TermsSection(
          title: '제1조',
          content: '서비스 이용약관 더미 본문입니다. 실제 서비스에서는 전체 약관이 표시됩니다.',
        ),
      ],
    );
  }

  void _onSubmit() {
    if (_allRequiredChecked) {
      HapticFeedback.mediumImpact();
      Navigator.of(context).pushReplacementNamed(RouteNames.kakaoAuth);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 그라데이션 효과
          Positioned(
            top: -80,
            left: -60,
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFFE9D5FF).withValues(alpha: 0.4),
                    const Color(0xFFE9D5FF).withValues(alpha: 0.1),
                    const Color(0x00E9D5FF),
                  ],
                ),
              ),
            ),
          ),
          // 메인 컨텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBackPressed: () => Navigator.of(context).pop()),
                // 스크롤 영역
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(24, 16, 24, 180),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 헤드라인
                        const _Headline(),
                        const SizedBox(height: 32),
                        // 약관 카드
                        _TermsCard(
                          allChecked: _allChecked,
                          onToggleAll: _toggleAll,
                          requiredTerms: _requiredTerms,
                          onToggleItem: _toggleItem,
                          onDetailPressed: _onDetailPressed,
                          marketingChecked: _marketingChecked,
                          onMarketingChanged: (value) {
                            setState(() => _marketingChecked = value);
                            HapticFeedback.selectionClick();
                          },
                          pushEnabled: _pushEnabled,
                          onPushChanged: (value) {
                            setState(() => _pushEnabled = value);
                            HapticFeedback.selectionClick();
                          },
                          emailEnabled: _emailEnabled,
                          onEmailChanged: (value) {
                            setState(() => _emailEnabled = value);
                            HapticFeedback.selectionClick();
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 버튼
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _BottomCTA(
                  isEnabled: _allRequiredChecked,
                  onPressed: _onSubmit,
                ),
                _TestAccountButton(onPressed: _enterWithTestAccount),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBackPressed;

  const _Header({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBackPressed,
            child: const Icon(
              CupertinoIcons.back,
              color: _AppColors.textMain,
              size: 24,
            ),
          ),
          const Expanded(
            child: Text(
              '약관 동의',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
          ),
          const SizedBox(width: 44),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤드라인
// =============================================================================
class _Headline extends StatelessWidget {
  const _Headline();

  @override
  Widget build(BuildContext context) {
    return RichText(
      text: const TextSpan(
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 28,
          fontWeight: FontWeight.w700,
          height: 1.3,
          letterSpacing: -0.5,
          color: _AppColors.textMain,
        ),
        children: [
          TextSpan(text: '서비스 이용을 위해\n'),
          TextSpan(
            text: '동의',
            style: TextStyle(color: _AppColors.primary),
          ),
          TextSpan(text: '가 필요해요'),
        ],
      ),
    );
  }
}

// =============================================================================
// 약관 카드
// =============================================================================
class _TermsCard extends StatelessWidget {
  final bool allChecked;
  final ValueChanged<bool> onToggleAll;
  final List<TermsItem> requiredTerms;
  final void Function(TermsItem, bool) onToggleItem;
  final ValueChanged<TermsItem> onDetailPressed;
  final bool marketingChecked;
  final ValueChanged<bool> onMarketingChanged;
  final bool pushEnabled;
  final ValueChanged<bool> onPushChanged;
  final bool emailEnabled;
  final ValueChanged<bool> onEmailChanged;

  const _TermsCard({
    required this.allChecked,
    required this.onToggleAll,
    required this.requiredTerms,
    required this.onToggleItem,
    required this.onDetailPressed,
    required this.marketingChecked,
    required this.onMarketingChanged,
    required this.pushEnabled,
    required this.onPushChanged,
    required this.emailEnabled,
    required this.onEmailChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.08),
            blurRadius: 40,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          // 전체 동의
          _AllAgreeRow(isChecked: allChecked, onChanged: onToggleAll),
          Container(height: 1, color: _AppColors.gray100),
          // 필수 항목들
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              children: requiredTerms.map((item) {
                return _TermsItemRow(
                  item: item,
                  onChanged: (value) => onToggleItem(item, value),
                  onDetailPressed: item.hasDetail
                      ? () => onDetailPressed(item)
                      : null,
                );
              }).toList(),
            ),
          ),
          // 선택 항목 (마케팅)
          Container(
            margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: _AppColors.gray100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _CustomCheckbox(
                      isChecked: marketingChecked,
                      onChanged: onMarketingChanged,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: RichText(
                        text: const TextSpan(
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.textSecondary,
                          ),
                          children: [
                            TextSpan(
                              text: '[선택] ',
                              style: TextStyle(
                                color: _AppColors.textMuted,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            TextSpan(text: '마케팅 정보 수신 동의'),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                // 토글 스위치들
                Padding(
                  padding: const EdgeInsets.only(left: 36),
                  child: Row(
                    children: [
                      Expanded(
                        child: _ToggleOption(
                          label: 'Push',
                          isEnabled: pushEnabled,
                          onChanged: onPushChanged,
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: _ToggleOption(
                          label: 'Email',
                          isEnabled: emailEnabled,
                          onChanged: onEmailChanged,
                        ),
                      ),
                    ],
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

// =============================================================================
// 전체 동의 행
// =============================================================================
class _AllAgreeRow extends StatelessWidget {
  final bool isChecked;
  final ValueChanged<bool> onChanged;

  const _AllAgreeRow({required this.isChecked, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => onChanged(!isChecked),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            _CustomCheckbox(isChecked: isChecked, onChanged: onChanged),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '약관 전체 동의',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '선택 포함 모든 약관에 동의합니다',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textMuted,
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
}

// =============================================================================
// 약관 항목 행
// =============================================================================
class _TermsItemRow extends StatelessWidget {
  final TermsItem item;
  final ValueChanged<bool> onChanged;
  final VoidCallback? onDetailPressed;

  const _TermsItemRow({
    required this.item,
    required this.onChanged,
    this.onDetailPressed,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => onChanged(!item.isChecked),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        child: Row(
          children: [
            _CustomCheckbox(isChecked: item.isChecked, onChanged: onChanged),
            const SizedBox(width: 12),
            Expanded(
              child: RichText(
                text: TextSpan(
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textSecondary,
                  ),
                  children: [
                    TextSpan(
                      text: item.isRequired ? '[필수] ' : '[선택] ',
                      style: TextStyle(
                        color: item.isRequired
                            ? _AppColors.primary
                            : _AppColors.textMuted,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    TextSpan(text: item.label),
                  ],
                ),
              ),
            ),
            if (onDetailPressed != null)
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size(32, 32),
                onPressed: onDetailPressed,
                child: const Icon(
                  CupertinoIcons.chevron_right,
                  size: 18,
                  color: _AppColors.gray300,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 커스텀 체크박스
// =============================================================================
class _CustomCheckbox extends StatelessWidget {
  final bool isChecked;
  final ValueChanged<bool> onChanged;

  const _CustomCheckbox({required this.isChecked, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => onChanged(!isChecked),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 24,
        height: 24,
        decoration: BoxDecoration(
          color: isChecked ? _AppColors.primary : CupertinoColors.white,
          shape: BoxShape.circle,
          border: Border.all(
            color: isChecked ? _AppColors.primary : _AppColors.gray200,
            width: 2,
          ),
        ),
        child: isChecked
            ? const Icon(
                CupertinoIcons.checkmark,
                size: 14,
                color: CupertinoColors.white,
              )
            : null,
      ),
    );
  }
}

// =============================================================================
// 토글 옵션
// =============================================================================
class _ToggleOption extends StatelessWidget {
  final String label;
  final bool isEnabled;
  final ValueChanged<bool> onChanged;

  const _ToggleOption({
    required this.label,
    required this.isEnabled,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: _AppColors.textMuted,
          ),
        ),
        CupertinoSwitch(
          value: isEnabled,
          activeTrackColor: _AppColors.primary,
          onChanged: onChanged,
        ),
      ],
    );
  }
}

// =============================================================================
// 하단 CTA 버튼
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final bool isEnabled;
  final VoidCallback onPressed;

  const _BottomCTA({required this.isEnabled, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight.withValues(alpha: 0.95),
            _AppColors.backgroundLight,
          ],
          stops: const [0.0, 0.3, 1.0],
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: isEnabled ? onPressed : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: isEnabled
                ? _AppColors.primary
                : _AppColors.primary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(28),
            boxShadow: isEnabled
                ? [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.35),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ]
                : [],
          ),
          child: Center(
            child: Text(
              '동의하고 시작하기',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: isEnabled
                    ? CupertinoColors.white
                    : CupertinoColors.white.withValues(alpha: 0.7),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TestAccountButton extends StatelessWidget {
  final VoidCallback onPressed;

  const _TestAccountButton({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 12),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: Container(
          width: double.infinity,
          height: 48,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: _AppColors.primary, width: 1.5),
            color: CupertinoColors.white,
          ),
          child: const Center(
            child: Text(
              '테스트 계정으로 둘러보기',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
