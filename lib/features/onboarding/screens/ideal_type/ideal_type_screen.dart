// =============================================================================
// 이상형 정보 입력 화면 (이상형 설정 개요)
// 경로: lib/features/onboarding/screens/ideal_type/ideal_type_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/onboarding/screens/ideal_type/ideal_type_screen.dart';
// ...
// home: const IdealTypeScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../../router/route_names.dart';
import '../../../../services/onboarding_save_helper.dart';
import '../../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF5468C);
  static const Color backgroundBase = Color(0xFFFAFAFA);
  static const Color surfaceWhite = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF111827);
  static const Color textSub = Color(0xFF6B7280);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color dotInactive = Color(0xFFEDE8EB);
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealTypeScreen extends StatefulWidget {
  const IdealTypeScreen({super.key});

  @override
  State<IdealTypeScreen> createState() => _IdealTypeScreenState();
}

class _IdealTypeScreenState extends State<IdealTypeScreen> {
  String? _height;
  String? _age;
  String? _mbti;
  String? _major;

  bool _isSkipping = false;

  bool get _hasAnyPreference =>
      _height != null || _age != null || _mbti != null || _major != null;

  static const Map<String, String> _majorLabelMap = {
    'liberalArts': '문과 계열',
    'science': '이과 계열',
    'medical': '메디컬 계열',
    'artsSports': '예체능 계열',
  };

  @override
  void initState() {
    super.initState();
    _loadSavedIdealType();
  }

  Future<void> _loadSavedIdealType() async {
    final storage = StorageService();
    final kakaoUserId = await storage.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final draft = await storage.getOnboardingDraft(kakaoUserId);
    if (!mounted) return;

    // idealHeight: {min: int, max: int}
    final idealHeight = draft['idealHeight'];
    if (idealHeight is Map) {
      final min = idealHeight['min'];
      final max = idealHeight['max'];
      if (min != null && max != null) {
        final mn = min is int ? min : int.tryParse(min.toString());
        final mx = max is int ? max : int.tryParse(max.toString());
        if (mn != null && mx != null) {
          _height = mn == mx ? '$mn' : '$mn - $mx';
        }
      }
    }

    // idealAge: {min: int, max: int}
    final idealAge = draft['idealAge'];
    if (idealAge is Map) {
      final min = idealAge['min'];
      final max = idealAge['max'];
      if (min != null && max != null) {
        final mn = min is int ? min : int.tryParse(min.toString());
        final mx = max is int ? max : int.tryParse(max.toString());
        if (mn != null && mx != null) {
          _age = mn == mx ? '$mn' : '$mn - $mx';
        }
      }
    }

    // idealMbti: {EI: 'E'|'I', NS: 'N'|'S', TF: 'T'|'F', JP: 'J'|'P'}
    final idealMbti = draft['idealMbti'];
    if (idealMbti is Map) {
      final parts = <String>[];
      for (final k in ['EI', 'NS', 'TF', 'JP']) {
        final v = idealMbti[k];
        if (v != null && v.toString().isNotEmpty) {
          parts.add(v.toString());
        }
      }
      if (parts.isNotEmpty) {
        _mbti = parts.join(', ');
      }
    }

    // idealDepartment: 단일 'artsSports' 또는 리스트 ['artsSports', 'liberalArts']
    final idealDepartment = draft['idealDepartment'];
    if (idealDepartment != null) {
      if (idealDepartment is List) {
        final labels = idealDepartment
            .map((e) => _majorLabelMap[e.toString()] ?? e.toString())
            .where((s) => s.isNotEmpty)
            .toList();
        _major = labels.isEmpty ? null : labels.join(', ');
      } else {
        final key = idealDepartment.toString();
        if (key.isNotEmpty) {
          _major = _majorLabelMap[key] ?? key;
        }
      }
    }

    setState(() {});
  }

  Future<void> _onSkipPressed() async {
    if (_isSkipping) return;
    HapticFeedback.lightImpact();
    setState(() => _isSkipping = true);
    await OnboardingSaveHelper.skipIdealType();
    if (!mounted) return;
    Navigator.of(
      context,
      rootNavigator: true,
    ).pushReplacementNamed(RouteNames.welcomeTutorial);
  }

  void _onHeightTap() {
    HapticFeedback.selectionClick();
    Navigator.of(context)
        .pushNamed(RouteNames.onboardingIdealHeight)
        .then((_) => _loadSavedIdealType());
  }

  void _onAgeTap() {
    HapticFeedback.selectionClick();
    Navigator.of(context)
        .pushNamed(RouteNames.onboardingIdealAge)
        .then((_) => _loadSavedIdealType());
  }

  void _onMbtiTap() {
    HapticFeedback.selectionClick();
    Navigator.of(context)
        .pushNamed(RouteNames.onboardingIdealMbti)
        .then((_) => _loadSavedIdealType());
  }

  void _onMajorTap() {
    HapticFeedback.selectionClick();
    Navigator.of(context)
        .pushNamed(RouteNames.onboardingIdealDepartment)
        .then((_) => _loadSavedIdealType());
  }

  void _onNextPressed() {
    HapticFeedback.mediumImpact();
    Navigator.of(context).pushNamed(RouteNames.onboardingIdealLifestyle);
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundBase,
      child: Stack(
        children: [
          const Positioned.fill(child: _SubtleBackgroundGradient()),
          SafeArea(
            bottom: false,
            child: Column(
              children: [
                _Header(
                  onBackPressed: () => Navigator.of(context).pop(),
                  onSkipPressed: _isSkipping ? null : () => _onSkipPressed(),
                  currentStep: 1,
                  totalSteps: 3,
                ),
                Expanded(
                  child: AnimatedOpacity(
                    opacity: _isSkipping ? 0.0 : 1.0,
                    duration: const Duration(milliseconds: 150),
                    curve: Curves.easeOut,
                    child: AnimatedScale(
                      scale: _isSkipping ? 0.96 : 1.0,
                      duration: const Duration(milliseconds: 150),
                      curve: Curves.easeOut,
                      child: SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 120),
                        child: _CardContainer(
                          child: Column(
                            children: [
                              const SizedBox(height: 24),
                              const _TitleSection(),
                              const SizedBox(height: 32),
                              _InputField(
                                label: '키',
                                value: _height ?? '상관없어요',
                                suffix: _height != null ? 'cm' : null,
                                icon: CupertinoIcons.resize_v,
                                onTap: _onHeightTap,
                              ),
                              const SizedBox(height: 20),
                              _InputField(
                                label: '나이',
                                value: _age ?? '상관없어요',
                                suffix: _age != null ? '살' : null,
                                icon: CupertinoIcons.gift,
                                onTap: _onAgeTap,
                              ),
                              const SizedBox(height: 20),
                              _InputField(
                                label: 'MBTI',
                                value: _mbti ?? '상관없어요',
                                icon: CupertinoIcons.circle_grid_hex,
                                onTap: _onMbtiTap,
                              ),
                              const SizedBox(height: 20),
                              _InputField(
                                label: '학과',
                                labelSuffix: '(중복 선택 가능)',
                                value: _major ?? '상관없어요',
                                icon: CupertinoIcons.book,
                                onTap: _onMajorTap,
                              ),
                              const SizedBox(height: 32),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: AnimatedOpacity(
              opacity: _isSkipping ? 0.0 : 1.0,
              duration: const Duration(milliseconds: 150),
              curve: Curves.easeOut,
              child: _BottomCTA(
                label: _hasAnyPreference ? '다음' : '그냥 넘어갈게요',
                onPressed: _onNextPressed,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SubtleBackgroundGradient extends StatelessWidget {
  const _SubtleBackgroundGradient();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            const Color(0xFFEDE8EB).withValues(alpha: 0.16),
            _AppColors.backgroundBase,
            CupertinoColors.white.withValues(alpha: 0.96),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBackPressed;
  final VoidCallback? onSkipPressed;
  final int currentStep;
  final int totalSteps;

  const _Header({
    required this.onBackPressed,
    this.onSkipPressed,
    required this.currentStep,
    required this.totalSteps,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        children: [
          SizedBox(
            width: 132,
            height: 44,
            child: Align(
              alignment: Alignment.centerLeft,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size(44, 44),
                onPressed: onBackPressed,
                child: const Icon(
                  CupertinoIcons.back,
                  color: _AppColors.textMain,
                  size: 24,
                ),
              ),
            ),
          ),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(totalSteps, (index) {
                final isActive = index == currentStep - 1;
                return AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  width: isActive ? 24 : 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: isActive
                        ? _AppColors.primary
                        : _AppColors.dotInactive,
                    borderRadius: BorderRadius.circular(5),
                  ),
                );
              }),
            ),
          ),
          SizedBox(
            width: 132,
            height: 44,
            child: _SkipLaterButton(onPressed: onSkipPressed),
          ),
        ],
      ),
    );
  }
}

class _SkipLaterButton extends StatefulWidget {
  final VoidCallback? onPressed;

  const _SkipLaterButton({this.onPressed});

  @override
  State<_SkipLaterButton> createState() => _SkipLaterButtonState();
}

class _SkipLaterButtonState extends State<_SkipLaterButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _offset;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 820),
    )..repeat(reverse: true);
    final curved = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    );
    _offset = Tween<Offset>(
      begin: const Offset(-0.025, 0),
      end: const Offset(0.025, 0),
    ).animate(curved);
    _opacity = Tween<double>(begin: 0.68, end: 1).animate(curved);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: SlideTransition(
        position: _offset,
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: widget.onPressed,
          child: Container(
            height: 34,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(17),
              border: Border.all(
                color: _AppColors.primary.withValues(alpha: 0.34),
              ),
            ),
            alignment: Alignment.center,
            child: const Text(
              '건너뛰고 다음에 할래요',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 11.5,
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

// =============================================================================
// 카드 컨테이너
// =============================================================================
class _CardContainer extends StatelessWidget {
  final Widget child;

  const _CardContainer({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: _AppColors.surfaceWhite,
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: child,
      ),
    );
  }
}

// =============================================================================
// 타이틀 섹션
// =============================================================================
class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        Text(
          '이상형 정보',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w800,
            color: _AppColors.textMain,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '매칭을 위해 이상형 정보를 입력해주세요.',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 입력 필드
// =============================================================================
class _InputField extends StatelessWidget {
  final String label;
  final String? labelSuffix;
  final String value;
  final String? suffix;
  final IconData icon;
  final VoidCallback onTap;

  const _InputField({
    required this.label,
    this.labelSuffix,
    required this.value,
    this.suffix,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 라벨
        Row(
          children: [
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            if (labelSuffix != null) ...[
              const SizedBox(width: 4),
              Text(
                labelSuffix!,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w400,
                  color: _AppColors.gray400,
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 12),
        // 입력 박스
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: onTap,
          child: Container(
            height: 52,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: _AppColors.gray50,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: _AppColors.gray100),
            ),
            child: Row(
              children: [
                Icon(icon, size: 18, color: _AppColors.gray400),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    value,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textSub,
                    ),
                  ),
                ),
                if (suffix != null) ...[
                  Text(
                    suffix!,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textSub,
                    ),
                  ),
                ],
                const SizedBox(width: 8),
                const Icon(
                  CupertinoIcons.chevron_right,
                  size: 16,
                  color: _AppColors.gray400,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 하단 CTA 버튼
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;

  const _BottomCTA({required this.label, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 24),
      decoration: BoxDecoration(
        color: _AppColors.backgroundBase.withValues(alpha: 0.9),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.24),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: CupertinoColors.white,
                ),
              ),
              const SizedBox(width: 6),
              const Icon(
                CupertinoIcons.arrow_right,
                size: 18,
                color: CupertinoColors.white,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
