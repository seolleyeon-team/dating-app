// =============================================================================
// 대나무숲(커뮤니티) 게시글 작성 화면
// 경로: lib/features/community/screens/post_write_screen.dart
//
// 디자인: 감정 선택 칩, Glassmorphism TextArea, 익명성 강조
// Firestore 게시글 등록 기능 연결
// =============================================================================

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:ui';
import 'dart:math' as math;

import 'package:provider/provider.dart';

import '../../../services/storage_service.dart';
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
  final StorageService _storageService = StorageService();

  final int _maxLength = 300;
  String _currentText = '';

  bool _isSubmitting = false;

  // 감정 태그 리스트
  final List<String> _emotions = ['#두근두근', '#첫미팅', '#짝사랑', '#비밀', '#설렘', '#고민'];

  String _selectedEmotion = '#두근두근';

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
      final kakaoUserId = await _storageService.getKakaoUserId();

      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인 정보가 없습니다.');
      }

      debugPrint('[PostWrite] 글 등록 authorId="$kakaoUserId"');

      final provider = context.read<CommunityProvider>();

      await provider.createPost(
        authorId: kakaoUserId,
        content: _currentText,
        category: _emotionToCategory(_selectedEmotion),
        tags: [_selectedEmotion],
      );

      if (!mounted) return;

      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('게시글 등록 실패: $e')));
    } finally {
      if (!mounted) return;

      setState(() {
        _isSubmitting = false;
      });
    }
  }

  // 감정 태그 → 카테고리 변환
  String _emotionToCategory(String emotion) {
    if (emotion.contains('설렘') || emotion.contains('두근')) return '설렘';
    if (emotion.contains('고민')) return '고민';
    return '일상';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _AppColors.backgroundLight,
      body: Stack(
        children: [
          const _BackgroundDecoration(),

          SafeArea(
            child: Column(
              children: [
                _Header(
                  onClose: () => Navigator.of(context).pop(),
                  onDraft: () {
                    HapticFeedback.lightImpact();
                  },
                ),

                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 24),
                          child: Text(
                            '어떤 마음인가요?',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                              color: _AppColors.textMain,
                              height: 1.2,
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // 감정 선택
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          child: Row(
                            children: _emotions.map((emotion) {
                              final isSelected = _selectedEmotion == emotion;

                              return Padding(
                                padding: const EdgeInsets.only(right: 12),
                                child: GestureDetector(
                                  onTap: () {
                                    HapticFeedback.selectionClick();
                                    setState(() => _selectedEmotion = emotion);
                                  },
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 20,
                                      vertical: 10,
                                    ),
                                    decoration: BoxDecoration(
                                      color: isSelected
                                          ? _AppColors.primary
                                          : Colors.white,
                                      borderRadius: BorderRadius.circular(20),
                                      border: Border.all(
                                        color: isSelected
                                            ? Colors.transparent
                                            : Colors.grey.withValues(
                                                alpha: 0.2,
                                              ),
                                      ),
                                    ),
                                    child: Text(
                                      emotion,
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: isSelected
                                            ? FontWeight.bold
                                            : FontWeight.w500,
                                        color: isSelected
                                            ? Colors.white
                                            : Colors.grey[600],
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
                                  color: Colors.white.withValues(alpha: 0.7),
                                  borderRadius: BorderRadius.circular(24),
                                ),
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _textController,
                                      maxLines: null,
                                      minLines: 8,
                                      maxLength: _maxLength,
                                      decoration: const InputDecoration(
                                        hintText:
                                            '솔직한 마음을 익명으로 남겨보세요...\n아무도 모를 거예요.',
                                        hintStyle: TextStyle(
                                          color: Colors.grey,
                                          height: 1.6,
                                          fontSize: 16,
                                        ),
                                        border: InputBorder.none,
                                        counterText: '',
                                      ),
                                      style: const TextStyle(
                                        fontSize: 16,
                                        height: 1.6,
                                        color: _AppColors.textMain,
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
                                              color: Colors.grey[400],
                                            ),
                                            const SizedBox(width: 4),
                                            Text(
                                              '익명 보장',
                                              style: TextStyle(
                                                fontSize: 12,
                                                color: Colors.grey[400],
                                              ),
                                            ),
                                          ],
                                        ),
                                        Text(
                                          '${_currentText.length}/$_maxLength자',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: Colors.grey[400],
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
                      onPressed: _currentText.isEmpty || _isSubmitting
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
                          ? const CircularProgressIndicator(color: Colors.white)
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
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [_AppColors.gradientStart, _AppColors.gradientEnd],
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
  final VoidCallback onDraft;

  const _Header({required this.onClose, required this.onDraft});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: onClose,
            icon: const Icon(Icons.close_rounded, size: 28),
          ),
          const Text(
            '대나무숲 글쓰기',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: _AppColors.textMain,
            ),
          ),
          TextButton(onPressed: onDraft, child: const Text('임시저장')),
        ],
      ),
    );
  }
}
