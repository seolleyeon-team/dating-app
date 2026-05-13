// =============================================================================
// 약관 동의 화면
// 경로: lib/features/onboarding/screens/terms_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/auth/screens/terms_screen.dart';
// ...
// home: const TermsScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../constants/legal_texts.dart';
import '../../../router/route_names.dart';
import 'terms_detail_sheet.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

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
    TermsItem(
      id: LegalTexts.serviceTerms.id,
      label: '서비스 이용약관 동의',
      isRequired: true,
      hasDetail: true,
    ),
    TermsItem(
      id: LegalTexts.privacyPolicy.id,
      label: '개인정보 처리방침 동의',
      isRequired: true,
      hasDetail: true,
    ),
    TermsItem(
      id: LegalTexts.kakaoNamePhoneConsent.id,
      label: '이름 및 전화번호 수집·이용 동의',
      isRequired: true,
      hasDetail: true,
    ),
    TermsItem(id: 'ageOver18', label: '만 18세 이상입니다', isRequired: true),
  ];

  bool _isSubmitting = false;
  bool _marketingChecked = false;
  bool _pushEnabled = false;
  bool _emailEnabled = false;

  bool get _allRequiredChecked =>
      _requiredTerms.every((item) => item.isChecked);

  bool get _allChecked => _allRequiredChecked && _marketingChecked;

  Future<void> _enterWithTestAccount() async {
    final storage = StorageService();
    final userService = UserService();
    await storage.saveKakaoUserId("fake_user_1");
    final existingProfile = await userService.getUserProfile('fake_user_1');
    if (existingProfile != null) {
      await userService.setLastActivePlatform(
        kakaoUserId: 'fake_user_1',
        platform: 'web',
      );
      await userService.saveLegalConsents(kakaoUserId: 'fake_user_1');
    }

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

  List<TermsSection> _sheetSectionsFor(LegalTextDocument document) {
    return document.sections
        .map(
          (section) =>
              TermsSection(title: section.title, content: section.content),
        )
        .toList();
  }

  LegalTextDocument? _documentFor(TermsItem item) {
    return LegalTexts.findById(item.id);
  }

  Future<void> _onDetailPressed(TermsItem item) async {
    final document = _documentFor(item);
    if (document == null) return;

    HapticFeedback.lightImpact();
    final didAgree = await TermsDetailSheet.show(
      context,
      title: document.title,
      sections: _sheetSectionsFor(document),
    );
    if (didAgree == true && mounted) {
      _toggleItem(item, true);
    }
  }

  Future<void> _onSubmit() async {
    if (!_allRequiredChecked || _isSubmitting) return;

    setState(() => _isSubmitting = true);
    try {
      await StorageService().savePendingLegalConsents();
      HapticFeedback.mediumImpact();
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(RouteNames.kakaoAuth);
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
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
                  isLoading: _isSubmitting,
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
              '필수 동의',
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '서비스 이용을 위한\n필수 동의',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 28,
            fontWeight: FontWeight.w700,
            height: 1.3,
            letterSpacing: -0.5,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(height: 14),
        const Text(
          '설레연은 안전한 대학생 인증 기반 매칭 커뮤니티 운영을 위해 필요한 최소한의 개인정보를 수집·이용합니다.',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 15,
            fontWeight: FontWeight.w500,
            height: 1.55,
            color: _AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: 14),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: _AppColors.primary.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: _AppColors.primary.withValues(alpha: 0.14),
            ),
          ),
          child: const Text(
            '이름과 전화번호는 카카오 로그인 과정에서 제공받을 수 있으며, 실사용자 확인, 중복 가입 방지, 신고 및 제재 대응 등 안전한 서비스 운영을 위해 사용됩니다.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w600,
              height: 1.55,
              color: _AppColors.textMain,
            ),
          ),
        ),
      ],
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
                    '전체 동의',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '필수 항목과 선택 항목을 한 번에 동의합니다',
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
                minimumSize: const Size(44, 32),
                onPressed: onDetailPressed,
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '보기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.primary,
                      ),
                    ),
                    SizedBox(width: 2),
                    Icon(
                      CupertinoIcons.chevron_right,
                      size: 15,
                      color: _AppColors.primary,
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
  final bool isLoading;

  const _BottomCTA({
    required this.isEnabled,
    required this.onPressed,
    required this.isLoading,
  });

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
        onPressed: isEnabled && !isLoading ? onPressed : null,
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
              isLoading ? '저장 중...' : '동의하고 시작하기',
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
