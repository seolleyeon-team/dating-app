// =============================================================================
// 자기소개 작성 화면 (온보딩 Step 5)
// 경로: lib/features/onboarding/screens/self_introduction_screen.dart
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textMuted = Color(0xFF89616F);
  static const Color borderLight = Color(0xFFE6DBDF);
  static const Color progressBg = Color(0xFFE6DBDF);
}

// =============================================================================
// 메인 화면
// =============================================================================
class SelfIntroductionScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final Function(String introduction)? onNext;

  const SelfIntroductionScreen({
    super.key,
    this.currentStep = 6,
    this.totalSteps = 8,
    this.onBack,
    this.onNext,
  });

  @override
  State<SelfIntroductionScreen> createState() => _SelfIntroductionScreenState();
}

class _SelfIntroductionScreenState extends State<SelfIntroductionScreen> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final UserService _userService = UserService();
  final StorageService _storageService = StorageService();

  int _charCount = 0;
  bool _isSavingOnExit = false;

  static const int _maxLength = 300;

  @override
  void initState() {
    super.initState();
    _loadExistingSelfIntroduction();
    _controller.addListener(() {
      setState(() {
        _charCount = _controller.text.length;
      });
    });
  }

  Future<void> _loadExistingSelfIntroduction() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;

    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;

    final intro = onboarding['selfIntroduction']?.toString() ?? '';
    _controller.text = intro;
    _charCount = intro.length;
  }

  Future<void> _saveCurrentSelfIntroduction() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;

    try {
      await OnboardingSaveHelper.saveSelfIntroduction(_controller.text.trim());
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentSelfIntroduction();
    if (!mounted) return;

    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _addSuggestion(String text) {
    final currentText = _controller.text;
    if (currentText.isNotEmpty && !currentText.endsWith('\n')) {
      _controller.text = '$currentText\n$text ';
    } else {
      _controller.text = '$currentText$text ';
    }
    _controller.selection = TextSelection.fromPosition(
      TextPosition(offset: _controller.text.length),
    );
    _focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handleBack();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: _AppColors.backgroundLight,
          resizeToAvoidBottomInset: false,
          body: SafeArea(
            child: Stack(
              children: [
                Column(
                  children: [
                    _Header(
                      currentStep: widget.currentStep,
                      totalSteps: widget.totalSteps,
                      onBack: _handleBack,
                    ),
                    Expanded(
                      child: SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(24, 0, 24, 100),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 16),
                            const Text(
                              '자기 소개',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 28,
                                fontWeight: FontWeight.bold,
                                height: 1.2,
                                color: _AppColors.textMain,
                              ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              '어떤 사람인지 알려주세요',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 15,
                                height: 1.5,
                                color: _AppColors.textMuted,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              '상대방에게 매력을 어필할 수 있는 기회예요.\n솔직하고 담백하게 작성해보세요.',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 15,
                                height: 1.5,
                                color: _AppColors.textMuted,
                              ),
                            ),
                            const SizedBox(height: 32),
                            _InputArea(
                              controller: _controller,
                              focusNode: _focusNode,
                              maxLength: _maxLength,
                              charCount: _charCount,
                            ),
                            const SizedBox(height: 32),
                            _SuggestionChipsArea(
                              onSuggestionSelected: _addSuggestion,
                            ),
                            SizedBox(
                              height: MediaQuery.of(context).viewInsets.bottom,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: _BottomButton(
                    onNext: () async {
                      HapticFeedback.mediumImpact();
                      await _saveCurrentSelfIntroduction();
                      if (!mounted) return;

                      if (widget.onNext != null) {
                        widget.onNext!.call(_controller.text);
                      } else {
                        Navigator.of(
                          context,
                        ).pushNamed(RouteNames.onboardingProfileQa);
                      }
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight.withValues(alpha: 0.8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: () async {
              HapticFeedback.lightImpact();
              if (onBack != null) {
                onBack!();
              } else {
                Navigator.of(context).pop();
              }
            },
            icon: const Icon(
              Icons.arrow_back_rounded,
              color: _AppColors.textMain,
              size: 24,
            ),
            style: IconButton.styleFrom(
              padding: const EdgeInsets.all(8),
              backgroundColor: Colors.transparent,
            ),
          ),
          Row(
            children: List.generate(totalSteps, (index) {
              final isCurrent = index == currentStep - 1;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: isCurrent ? 24 : 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: isCurrent ? _AppColors.primary : _AppColors.progressBg,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

// =============================================================================
// 텍스트 입력 영역
// =============================================================================
class _InputArea extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final int maxLength;
  final int charCount;

  const _InputArea({
    required this.controller,
    required this.focusNode,
    required this.maxLength,
    required this.charCount,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
        border: Border.all(
          color: focusNode.hasFocus
              ? _AppColors.primary
              : _AppColors.borderLight,
          width: focusNode.hasFocus ? 2 : 1,
        ),
      ),
      child: Stack(
        children: [
          TextField(
            controller: controller,
            focusNode: focusNode,
            maxLength: maxLength,
            maxLines: 8,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 16,
              height: 1.6,
              color: _AppColors.textMain,
            ),
            decoration: const InputDecoration(
              hintText: '커피 한 잔과 함께하는 조용한 대화를 좋아해요.\n주말에는 주로 한강에서 러닝을 즐겨요...',
              hintStyle: TextStyle(
                color: _AppColors.textMuted,
                fontSize: 16,
                height: 1.6,
              ),
              border: InputBorder.none,
              contentPadding: EdgeInsets.fromLTRB(20, 20, 20, 40),
              counterText: '',
            ),
            cursorColor: _AppColors.primary,
          ),
          Positioned(
            bottom: 16,
            right: 20,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight.withValues(alpha: 0.8),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Text(
                    '$charCount',
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: _AppColors.primary,
                    ),
                  ),
                  Text(
                    ' / $maxLength',
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textMuted,
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
// 추천 키워드 영역
// =============================================================================
class _SuggestionChipsArea extends StatelessWidget {
  final Function(String) onSuggestionSelected;

  const _SuggestionChipsArea({required this.onSuggestionSelected});

  static const List<Map<String, String>> _suggestions = [
    {'icon': '💊', 'text': '요즘 빠진 것'},
    {'icon': '🧗', 'text': '주말 루틴'},
    {'icon': '🍷', 'text': '좋아하는 데이트'},
    {'icon': '✈️', 'text': '가고싶은 여행지'},
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: const [
            Icon(Icons.lightbulb_rounded, color: _AppColors.primary, size: 20),
            SizedBox(width: 8),
            Text(
              '무엇을 쓸지 고민되시나요?',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: _AppColors.textMain,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: _suggestions.map((suggestion) {
            return _SuggestionChip(
              icon: suggestion['icon']!,
              label: suggestion['text']!,
              onTap: () {
                HapticFeedback.lightImpact();
                onSuggestionSelected('${suggestion['text']}: ');
              },
            );
          }).toList(),
        ),
      ],
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  final String icon;
  final String label;
  final VoidCallback onTap;

  const _SuggestionChip({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _AppColors.borderLight),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.02),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(icon, style: const TextStyle(fontSize: 14)),
            const SizedBox(width: 8),
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.textMuted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 버튼
// =============================================================================
class _BottomButton extends StatelessWidget {
  final VoidCallback? onNext;

  const _BottomButton({this.onNext});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight.withValues(alpha: 0.95),
            _AppColors.backgroundLight,
          ],
        ),
      ),
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        MediaQuery.of(context).padding.bottom + 20,
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onNext,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 12,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Text(
                '다음',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              SizedBox(width: 8),
              Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
