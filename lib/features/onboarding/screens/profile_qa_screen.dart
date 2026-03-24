// =============================================================================
// 프로필 문답 화면 (온보딩 Step 6)
// 경로: lib/features/onboarding/screens/profile_qa_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const ProfileQaScreen()),
// );
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
  static const Color textSub = Color(0xFF89616F);
  static const Color textGray = Color(0xFF9CA3AF);
  static const Color border = Color(0xFFE5E7EB);
  static const Color progressBg = Color(0xFFE6DBDF);
}

// =============================================================================
// 데이터 모델
// =============================================================================
class ProfileQuestion {
  final int id;
  final String question;
  String? answer;

  ProfileQuestion({required this.id, required this.question, this.answer});
}

// =============================================================================
// 메인 화면
// =============================================================================
class ProfileQaScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final VoidCallback? onComplete;
  final VoidCallback? onSkip;

  const ProfileQaScreen({
    super.key,
    this.currentStep = 7,
    this.totalSteps = 8,
    this.onBack,
    this.onComplete,
    this.onSkip,
  });

  @override
  State<ProfileQaScreen> createState() => _ProfileQaScreenState();
}

class _ProfileQaScreenState extends State<ProfileQaScreen> {
  // 초기 질문 데이터
  final List<ProfileQuestion> _questions = [
    ProfileQuestion(id: 1, question: '주말에 보통 뭐 해요?'),
    ProfileQuestion(id: 2, question: '가장 좋아하는 음식은?'),
    ProfileQuestion(id: 3, question: '나의 힐링 포인트는?'),
    ProfileQuestion(id: 4, question: '기억에 남는 여행지는?'),
    ProfileQuestion(id: 5, question: '내 이상형에 가까운 사람은?'),
  ];

  int? _expandedIndex = 0; // 초기에 첫 번째 질문 펼침
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;

  @override
  void initState() {
    super.initState();
    _loadExistingProfileQa();
  }

  Future<void> _loadExistingProfileQa() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;
    final profileQaRaw = onboarding['profileQa'];
    if (profileQaRaw is! List || profileQaRaw.isEmpty) return;
    for (final item in profileQaRaw) {
      if (item is! Map) continue;
      final q = item['question']?.toString() ?? '';
      final a = item['answer']?.toString() ?? '';
      if (q.isEmpty) continue;
      final idx = _questions.indexWhere((x) => x.question == q);
      if (idx >= 0) _questions[idx].answer = a.isNotEmpty ? a : null;
    }
    if (mounted) setState(() {});
  }

  Future<void> _saveCurrentProfileQa() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveProfileQa(
        _questions
            .where((q) => q.answer != null && q.answer!.isNotEmpty)
            .map((q) => {'question': q.question, 'answer': q.answer!})
            .toList(),
      );
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentProfileQa();
    if (!mounted) return;
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  void _toggleExpand(int index) {
    HapticFeedback.lightImpact();
    setState(() {
      if (_expandedIndex == index) {
        _expandedIndex = null; // 이미 펼쳐진 것 클릭 시 접음
      } else {
        _expandedIndex = index;
      }
    });
  }

  void _updateAnswer(int index, String value) {
    setState(() {
      _questions[index].answer = value;
    });
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
          resizeToAvoidBottomInset: true,
          body: SafeArea(
            child: Stack(
              children: [
                Column(
                  children: [
                    // 헤더
                    _Header(
                      currentStep: widget.currentStep,
                      totalSteps: widget.totalSteps,
                      onBack: _handleBack,
                    ),
                  // 메인 콘텐츠
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 120),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: 16),
                          // 헤드라인
                          const _Headline(),
                          const SizedBox(height: 24),
                          // 질문 리스트
                          ListView.separated(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            itemCount: _questions.length,
                            separatorBuilder: (context, index) =>
                                const SizedBox(height: 12),
                            itemBuilder: (context, index) {
                              return _QuestionCard(
                                question: _questions[index],
                                index: index,
                                isExpanded: _expandedIndex == index,
                                onTap: () => _toggleExpand(index),
                                onAnswerChanged: (value) =>
                                    _updateAnswer(index, value),
                              );
                            },
                          ),
                          const SizedBox(height: 32),
                          // 건너뛰기 버튼
                          Center(
                            child: CupertinoButton(
                              onPressed: () {
                                HapticFeedback.lightImpact();
                                widget.onSkip?.call();
                              },
                              child: const Text(
                                '다음에 입력하기 (건너뛰기)',
                                style: TextStyle(
                                  fontFamily: 'Noto Sans KR',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                  color: _AppColors.textGray,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 40),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              // 하단 완료 버튼
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
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
                    onPressed: () async {
                      HapticFeedback.mediumImpact();
                      await _saveCurrentProfileQa();
                      if (!mounted) return;
                      if (widget.onComplete != null) {
                        widget.onComplete!.call();
                      } else {
                        Navigator.of(context)
                            .pushNamed(RouteNames.onboardingKeywords);
                      }
                    },
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
                      child: const Center(
                        child: Text(
                          '다음',
                          style: TextStyle(
                            fontFamily: 'Noto Sans KR',
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ),
                  ),
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
            onPressed: () {
              HapticFeedback.lightImpact();
              if (onBack != null) {
                onBack!.call();
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
          // 커스텀 프로그레스 인디케이터
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
// 헤드라인
// =============================================================================
class _Headline extends StatelessWidget {
  const _Headline();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 메인 타이틀
        const Text(
          '프로필 문답',
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: _AppColors.textMain,
            height: 1.2,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 12),
        // 서브 타이틀
        RichText(
          text: const TextSpan(
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 15,
              color: _AppColors.textSub,
              height: 1.5,
            ),
            children: [
              TextSpan(text: '나를 표현하는 '),
              TextSpan(
                text: '문답',
                style: TextStyle(
                  color: _AppColors.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
              TextSpan(text: '을 작성해주세요'),
            ],
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          '솔직한 답변은 매력적인 프로필을 만들어요.',
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 14,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 질문 카드
// =============================================================================
class _QuestionCard extends StatelessWidget {
  final ProfileQuestion question;
  final int index;
  final bool isExpanded;
  final VoidCallback onTap;
  final Function(String) onAnswerChanged;

  const _QuestionCard({
    required this.question,
    required this.index,
    required this.isExpanded,
    required this.onTap,
    required this.onAnswerChanged,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        boxShadow: isExpanded
            ? [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.08),
                  blurRadius: 20,
                  offset: const Offset(0, 4),
                ),
              ]
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
        border: Border.all(
          color: isExpanded
              ? _AppColors.primary.withValues(alpha: 0.2)
              : Colors.transparent,
          width: 2,
        ),
      ),
      child: Column(
        children: [
          // 카드 헤더 (클릭 시 토글)
          GestureDetector(
            onTap: onTap,
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'QUESTION ${(index + 1).toString().padLeft(2, '0')}',
                          style: TextStyle(
                            fontFamily: 'Noto Sans KR',
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: isExpanded
                                ? _AppColors.primary
                                : _AppColors.textGray,
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          question.question,
                          style: const TextStyle(
                            fontFamily: 'Noto Sans KR',
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: _AppColors.textMain,
                            height: 1.4,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: isExpanded
                          ? Colors.transparent
                          : _AppColors.backgroundLight,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      isExpanded ? Icons.edit_note_rounded : Icons.add_rounded,
                      color: _AppColors.primary,
                      size: 22,
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 펼쳐진 상태: 입력 필드
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
            child: isExpanded
                ? Padding(
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                    child: Stack(
                      children: [
                        TextField(
                          controller:
                              TextEditingController(text: question.answer)
                                ..selection = TextSelection.fromPosition(
                                  TextPosition(
                                    offset: question.answer?.length ?? 0,
                                  ),
                                ),
                          onChanged: onAnswerChanged,
                          maxLength: 100,
                          maxLines: 4,
                          style: const TextStyle(
                            fontFamily: 'Noto Sans KR',
                            fontSize: 15,
                            height: 1.6,
                            color: _AppColors.textMain,
                          ),
                          decoration: InputDecoration(
                            hintText: '짧게라도 좋아요! 취미나 휴식 방법을 알려주세요.',
                            hintStyle: const TextStyle(
                              fontFamily: 'Noto Sans KR',
                              color: _AppColors.textGray,
                              fontSize: 14,
                            ),
                            fillColor: _AppColors.backgroundLight,
                            filled: true,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: _AppColors.border,
                              ),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: _AppColors.border,
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: _AppColors.primary,
                              ),
                            ),
                            contentPadding: const EdgeInsets.all(16),
                            counterText: '',
                          ),
                        ),
                        Positioned(
                          bottom: 12,
                          right: 12,
                          child: Text(
                            '${question.answer?.length ?? 0}/100',
                            style: const TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                              color: _AppColors.textGray,
                            ),
                          ),
                        ),
                      ],
                    ),
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}
