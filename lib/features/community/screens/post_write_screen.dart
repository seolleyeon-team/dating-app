// =============================================================================
// 대나무숲(커뮤니티) 게시글 작성 화면
// 경로: lib/features/community/screens/post_write_screen.dart
//
// 변경 사항:
// - 글쓰기 카테고리를 메인 화면과 동일하게 통일
// - 사용 카테고리: 설렘 / 고민 / 일상 / 질문
// - 기존 감정 태그(#두근두근 등) 제거
// =============================================================================

import 'dart:ui';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../../../core/constants/app_colors.dart';
import '../providers/community_provider.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color backgroundLight = Color(0xFFF8F6F7);
  static const Color gradientStart = Color(0xFFFFF0F5);
  static const Color gradientEnd = Color(0xFFF8F6F7);

  static const Color textMain = Color(0xFF181114);

  static const Color categoryRomanceBg = Color(0xFFFFEFF4);
  static const Color categoryRomanceText = Color(0xFFE85D93);

  static const Color categoryWorryBg = Color(0xFFFFF4E8);
  static const Color categoryWorryText = Color(0xFFDC8B2F);

  static const Color categoryDailyBg = Color(0xFFEFF7F0);
  static const Color categoryDailyText = Color(0xFF4E9B63);

  static const Color categoryQuestionBg = Color(0xFFEEF4FF);
  static const Color categoryQuestionText = Color(0xFF5E86E5);
}

// =============================================================================
// 메인 화면
// =============================================================================
class PostWriteScreen extends StatefulWidget {
  const PostWriteScreen({super.key});

  @override
  State<PostWriteScreen> createState() => _PostWriteScreenState();
}

class _PostWriteScreenState extends State<PostWriteScreen> {
  final TextEditingController _textController = TextEditingController();

  final int _maxLength = 300;
  String _currentText = '';
  bool _isSubmitting = false;

  // 메인 대나무숲과 동일한 카테고리
  final List<String> _categories = const ['설렘', '고민', '일상', '질문'];
  String _selectedCategory = '설렘';

  @override
  void initState() {
    super.initState();
    _textController.addListener(() {
      setState(() {
        _currentText = _textController.text;
      });
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  // =============================================================================
  // 게시글 등록
  // =============================================================================
  Future<void> _submitPost() async {
    if (_currentText.trim().isEmpty || _isSubmitting) return;

    FocusScope.of(context).unfocus();
    HapticFeedback.mediumImpact();

    setState(() {
      _isSubmitting = true;
    });

    try {
      final appUserId = FirebaseAuth.instance.currentUser?.uid.trim() ?? '';
      if (appUserId.isEmpty) {
        throw StateError('로그인 세션을 확인하지 못했어요. 다시 로그인해주세요.');
      }

      debugPrint(
        '[PostWrite] 글 등록 author=${PrivacyLogUtils.idFingerprint(appUserId)}, category="$_selectedCategory"',
      );

      if (!mounted) return;
      final provider = context.read<CommunityProvider>();

      final postId = await provider.createPost(
        authorId: appUserId,
        content: _currentText.trim(),
        category: _selectedCategory,
        tags: [_selectedCategory],
      );
      if (postId.isEmpty) {
        throw StateError('게시글을 저장하지 못했어요. 잠시 후 다시 시도해주세요.');
      }

      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      debugPrint('[PostWrite] 글 등록 실패: ${PrivacyLogUtils.errorSummary(e)}');
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(_failureMessage(e))));
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  String _failureMessage(Object error) {
    if (error is FirebaseException) {
      switch (error.code) {
        case 'permission-denied':
        case 'unauthenticated':
          return '글쓰기 권한을 확인하지 못했어요. 다시 로그인한 뒤 시도해주세요.';
        case 'unavailable':
        case 'deadline-exceeded':
          return '네트워크 연결을 확인한 뒤 다시 시도해주세요.';
      }
    }

    if (error is StateError) return error.message.toString();
    return '게시글을 등록하지 못했어요. 잠시 후 다시 시도해주세요.';
  }

  Color _getCategoryBackgroundColor(
    BuildContext context,
    String category,
    bool isSelected,
  ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    if (isSelected) {
      switch (category) {
        case '설렘':
          return _AppColors.categoryRomanceText;
        case '고민':
          return _AppColors.categoryWorryText;
        case '일상':
          return _AppColors.categoryDailyText;
        case '질문':
          return _AppColors.categoryQuestionText;
      }
    }

    switch (category) {
      case '설렘':
        return isDark ? const Color(0xFF33212C) : _AppColors.categoryRomanceBg;
      case '고민':
        return isDark ? const Color(0xFF332D20) : _AppColors.categoryWorryBg;
      case '일상':
        return isDark ? const Color(0xFF1F3028) : _AppColors.categoryDailyBg;
      case '질문':
        return isDark ? const Color(0xFF202B3B) : _AppColors.categoryQuestionBg;
      default:
        return isDark ? AppColorsDark.surface : Colors.white;
    }
  }

  Color _getCategoryTextColor(
    BuildContext context,
    String category,
    bool isSelected,
  ) {
    if (isSelected) return Colors.white;

    switch (category) {
      case '설렘':
        return _AppColors.categoryRomanceText;
      case '고민':
        return _AppColors.categoryWorryText;
      case '일상':
        return _AppColors.categoryDailyText;
      case '질문':
        return _AppColors.categoryQuestionText;
      default:
        return Colors.grey[700]!;
    }
  }

  String _getHintText() {
    switch (_selectedCategory) {
      case '설렘':
        return '설레는 순간이나 연애 이야기를 익명으로 남겨보세요...\n예: 요즘 자꾸 생각나는 사람이 있어요.';
      case '고민':
        return '혼자 고민하던 이야기를 편하게 남겨보세요...\n예: 상대가 나를 좋아하는 건지 헷갈려요.';
      case '일상':
        return '연애와 관련된 소소한 일상을 자유롭게 적어보세요...\n예: 오늘 캠퍼스에서 이런 일이 있었어요.';
      case '질문':
        return '다른 사람들의 의견이 궁금한 질문을 남겨보세요...\n예: 첫 연락은 어느 정도 텀으로 하는 게 좋나요?';
      default:
        return '솔직한 마음을 익명으로 남겨보세요...';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final surface = isDark ? AppColorsDark.surface : Colors.white;
    final textMain = isDark ? AppColorsDark.textPrimary : _AppColors.textMain;
    final muted = isDark ? AppColorsDark.textHint : Colors.grey[400]!;
    return Scaffold(
      backgroundColor: isDark
          ? AppColorsDark.background
          : _AppColors.backgroundLight,
      body: Stack(
        children: [
          const _BackgroundDecoration(),
          SafeArea(
            child: Column(
              children: [
                _Header(onClose: () => Navigator.of(context).pop()),
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: EdgeInsets.symmetric(horizontal: 24),
                          child: Text(
                            '어떤 카테고리의 글인가요?',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                              color: textMain,
                              height: 1.2,
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // 카테고리 선택
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          child: Row(
                            children: _categories.map((category) {
                              final isSelected = _selectedCategory == category;

                              return Padding(
                                padding: const EdgeInsets.only(right: 12),
                                child: GestureDetector(
                                  onTap: () {
                                    HapticFeedback.selectionClick();
                                    setState(() {
                                      _selectedCategory = category;
                                    });
                                  },
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 20,
                                      vertical: 10,
                                    ),
                                    decoration: BoxDecoration(
                                      color: _getCategoryBackgroundColor(
                                        context,
                                        category,
                                        isSelected,
                                      ),
                                      borderRadius: BorderRadius.circular(20),
                                      border: Border.all(
                                        color: isSelected
                                            ? Colors.transparent
                                            : _getCategoryTextColor(
                                                context,
                                                category,
                                                false,
                                              ).withValues(alpha: 0.18),
                                      ),
                                    ),
                                    child: Text(
                                      category,
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: isSelected
                                            ? FontWeight.bold
                                            : FontWeight.w600,
                                        color: _getCategoryTextColor(
                                          context,
                                          category,
                                          isSelected,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                        ),

                        const SizedBox(height: 24),

                        // 입력 영역
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(24),
                            child: BackdropFilter(
                              filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                              child: Container(
                                constraints: const BoxConstraints(
                                  minHeight: 300,
                                ),
                                padding: const EdgeInsets.all(24),
                                decoration: BoxDecoration(
                                  color: surface.withValues(alpha: 0.82),
                                  borderRadius: BorderRadius.circular(24),
                                ),
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _textController,
                                      maxLines: null,
                                      minLines: 8,
                                      maxLength: _maxLength,
                                      decoration: InputDecoration(
                                        hintText: _getHintText(),
                                        hintStyle: TextStyle(
                                          fontFamily: 'Pretendard',
                                          color: isDark
                                              ? AppColorsDark.textHint
                                              : Colors.grey,
                                          height: 1.6,
                                          fontSize: 16,
                                        ),
                                        border: InputBorder.none,
                                        counterText: '',
                                      ),
                                      style: TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontSize: 16,
                                        height: 1.6,
                                        color: textMain,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                    const SizedBox(height: 16),
                                    Row(
                                      mainAxisAlignment:
                                          MainAxisAlignment.spaceBetween,
                                      children: [
                                        Row(
                                          children: [
                                            Icon(
                                              Icons.lock_outline_rounded,
                                              size: 16,
                                              color: muted,
                                            ),
                                            const SizedBox(width: 4),
                                            Text(
                                              '익명 보장',
                                              style: TextStyle(
                                                fontSize: 12,
                                                color: muted,
                                              ),
                                            ),
                                          ],
                                        ),
                                        Text(
                                          '${_currentText.length}/$_maxLength자',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: muted,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                // 등록 버튼
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
                  child: SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton(
                      onPressed: _currentText.trim().isEmpty || _isSubmitting
                          ? null
                          : _submitPost,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _AppColors.primary,
                        disabledBackgroundColor: _AppColors.primary.withValues(
                          alpha: 0.3,
                        ),
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                      child: _isSubmitting
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2.4,
                              ),
                            )
                          : Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: const [
                                Text(
                                  '등록하기',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                SizedBox(width: 8),
                                Icon(Icons.send_rounded, size: 20),
                              ],
                            ),
                    ),
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
// 배경 장식
// =============================================================================
class _BackgroundDecoration extends StatelessWidget {
  const _BackgroundDecoration();

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: isDark
              ? const [Color(0xFF281923), AppColorsDark.background]
              : const [_AppColors.gradientStart, _AppColors.gradientEnd],
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onClose;

  const _Header({required this.onClose});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final text = isDark ? AppColorsDark.textPrimary : _AppColors.textMain;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: onClose,
            icon: Icon(Icons.close_rounded, size: 28, color: text),
          ),
          Text(
            '대나무숲 글쓰기',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: text,
            ),
          ),
          const SizedBox(width: 48),
        ],
      ),
    );
  }
}
