// =============================================================================
// Today's AI Match 카드 화면
// 경로: lib/features/matching/screens/ai_match_card_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const AiMatchCardScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';
import '../../../shared/widgets/seol_swipe_deck.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFE05281);
  static const Color primaryWarm = Color(0xFFFF99B3);
  static const Color textMain = Color(0xFF2F3438);
  static const Color textSub = Color(0xFF8B95A1);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
}

// =============================================================================
// 프로필 데이터
// =============================================================================
class _MatchProfile {
  final String name;
  final int age;
  final String university;
  final String major;
  final int matchPercent;
  final String imageUrl;

  const _MatchProfile({
    required this.name,
    required this.age,
    required this.university,
    required this.major,
    required this.matchPercent,
    required this.imageUrl,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class AiMatchCardScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final VoidCallback? onQna;
  final VoidCallback? onPass;
  final VoidCallback? onLike;
  final VoidCallback? onMessage;
  final Function(int index)? onNavTap;

  const AiMatchCardScreen({
    super.key,
    this.onBack,
    this.onQna,
    this.onPass,
    this.onLike,
    this.onMessage,
    this.onNavTap,
  });

  static const List<_MatchProfile> _profiles = [
    _MatchProfile(
      name: 'Ji-min Kim',
      age: 22,
      university: 'Seoul National University',
      major: 'Visual Design Major',
      matchPercent: 98,
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDpIxhHnYDkmD9z4U531npC8ZOpcgsNx5XJm96MbnNDjgdLpbH0-ZITCknT1WQTMor_kO8HJdn9gYk-VqSrCCin6Lx5nw-vM6QKH_lv1Mh8MPEypmEUXk3zczihAiAPhOMJYJgtEyA6ObIcE6qlGhH-23M6k6HTvLH57RtTbCprjgrx7Wg7Dy55ajq_YM9ABafQfkWyfZeAAX0qoE69mVQk2hACXRj6HRcmBira18n_hGrYPZEdP209XcwjPxAWn_op8Va1qvtAaD6P',
    ),
    _MatchProfile(
      name: 'Soo-yeon Park',
      age: 23,
      university: 'Yonsei University',
      major: 'Psychology',
      matchPercent: 94,
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuA-iKoOfd7mUBhLCu8omhZBXx588zQSVaTuUyPxd8tn5HGIqbofexG6xV_wpU-m1DwzanC-9eZa9On_1heZiGjjrRZfW2q-4u5XMCegZ3-FWSb_vFcW2Q-ekVQFZTaKtT8ja--_6YV71R2iJjLA0J91Y1Jnp0SbXNEjmIBvH9TIoHyXY-ErSnUZaRjEhcBVmhOpChRqBrF0r5YpiKtqSi8G8DdMop8R7kiJGLKFoChyCmRyqHE7EB-Km7q6kjBctextaAUtbZwKHDEX',
    ),
    _MatchProfile(
      name: 'Ha-eun Lee',
      age: 21,
      university: 'Korea University',
      major: 'Computer Science',
      matchPercent: 91,
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCZm5OPNQsqWRtn9Q9JRanlA3wGHr2RQpXGWBvXeoJPFMH3ceEkM35k27hOD-SdpW-emSzqFGV1iNHDuvl2-JwD7CohYcY2aC2QMqSvZs2v8obekQXSOa0AJVb9LaO0VT1Gl6rJSMo96FU8_eRYPWNo3_aDOGfEqgjj4W95XZEZIKHfzf_tQda6Qz5X-cE4oBscYXjQeAILJRSjk-xOWqPKxhKKb4_R1kiCzG_BqnVtDKzzdrAYqaJ03uY7RMGrxLqF03aL5KJQgqS_',
    ),
  ];

  @override
  State<AiMatchCardScreen> createState() => _AiMatchCardScreenState();
}

class _AiMatchCardScreenState extends State<AiMatchCardScreen> {
  final _deckController = SeolSwipeDeckController();

  void _onSwiped(int index, SwipeDirection direction) {
    if (direction == SwipeDirection.right) {
      widget.onLike?.call();
    } else {
      widget.onPass?.call();
    }
  }

  void _onLike() {
    HapticFeedback.mediumImpact();
    _deckController.swipeRight();
  }

  void _onPass() {
    HapticFeedback.lightImpact();
    _deckController.swipeLeft();
  }

  @override
  void dispose() {
    _deckController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.white,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: CupertinoColors.white,
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            if (widget.onBack != null) {
              widget.onBack!();
            } else {
              Navigator.of(context, rootNavigator: true).pop();
            }
          },
          child: const Icon(
            CupertinoIcons.back,
            size: 24,
            color: _AppColors.textMain,
          ),
        ),
        middle: const Text(
          "Today's AI Match",
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: Stack(
        children: [
          // 메인 컨텐츠
          SafeArea(
            child: Column(
              children: [
                // 스와이프 카드 덱
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: SeolSwipeDeck(
                      controller: _deckController,
                      onSwiped: _onSwiped,
                      cards: AiMatchCardScreen._profiles
                          .map((p) => _MainCard(profile: p))
                          .toList(),
                    ),
                  ),
                ),
                // 액션 버튼
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
                  child: _ActionButtons(
                    onQna: widget.onQna,
                    onPass: _onPass,
                    onLike: _onLike,
                    onMessage: widget.onMessage,
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
// 메인 카드
// =============================================================================
class _MainCard extends StatelessWidget {
  final _MatchProfile profile;

  const _MainCard({required this.profile});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: _AppColors.gray100.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.15),
            blurRadius: 40,
            offset: const Offset(0, 20),
          ),
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 15,
            offset: const Offset(0, 0),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          // 이미지 영역 (72%)
          Expanded(
            flex: 72,
            child: Stack(
              fit: StackFit.expand,
              children: [
                // 프로필 이미지
                Image.network(
                  profile.imageUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      Container(color: _AppColors.gray100),
                ),
                // AI Match 배지
                Positioned(
                  top: 16,
                  left: 16,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: CupertinoColors.white.withValues(alpha: 0.9),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: CupertinoColors.white.withValues(alpha: 0.5),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: CupertinoColors.black.withValues(alpha: 0.05),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          CupertinoIcons.sparkles,
                          size: 18,
                          color: _AppColors.primary,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'AI Match ${profile.matchPercent}%',
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.3,
                            color: _AppColors.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                // 하단 그라데이션
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  height: 48,
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          CupertinoColors.black.withValues(alpha: 0),
                          CupertinoColors.black.withValues(alpha: 0.1),
                        ],
                      ),
                    ),
                  ),
                ),
                // 프로필 상세 버튼
                Positioned(
                  top: 16,
                  right: 16,
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      Navigator.of(
                        context,
                      ).pushNamed(RouteNames.profileSpecificDetail);
                    },
                    child: Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: CupertinoColors.black.withValues(alpha: 0.2),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        CupertinoIcons.chevron_down,
                        size: 20,
                        color: CupertinoColors.white,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 프로필 정보 영역 (28%)
          Expanded(
            flex: 28,
            child: Container(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // 이름 & 나이
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Text(
                        profile.name,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 24,
                          fontWeight: FontWeight.w800,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${profile.age}',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textSub,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // 대학교
                  Row(
                    children: [
                      Icon(
                        CupertinoIcons.building_2_fill,
                        size: 18,
                        color: _AppColors.primary.withValues(alpha: 0.7),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        profile.university,
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textMain.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  // 전공
                  Row(
                    children: [
                      const Icon(
                        CupertinoIcons.paintbrush,
                        size: 18,
                        color: _AppColors.textSub,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        profile.major,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textSub,
                        ),
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

// =============================================================================
// 액션 버튼
// =============================================================================
class _ActionButtons extends StatelessWidget {
  final VoidCallback? onQna;
  final VoidCallback? onPass;
  final VoidCallback? onLike;
  final VoidCallback? onMessage;

  const _ActionButtons({this.onQna, this.onPass, this.onLike, this.onMessage});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        _ActionButton(
          icon: CupertinoIcons.person_2,
          label: 'Q&A',
          onPressed: onQna,
        ),
        _ActionButton(
          icon: CupertinoIcons.xmark,
          label: 'Pass',
          onPressed: onPass,
        ),
        _ActionButton(
          icon: CupertinoIcons.heart_fill,
          label: 'Like',
          isPrimary: true,
          backgroundColor: _AppColors.primaryWarm,
          onPressed: onLike,
        ),
        _ActionButton(
          icon: CupertinoIcons.chat_bubble_fill,
          label: 'Message',
          isPrimary: true,
          backgroundColor: _AppColors.primary,
          textColor: _AppColors.primary,
          onPressed: onMessage,
        ),
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isPrimary;
  final Color? backgroundColor;
  final Color? textColor;
  final VoidCallback? onPressed;

  const _ActionButton({
    required this.icon,
    required this.label,
    this.isPrimary = false,
    this.backgroundColor,
    this.textColor,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.mediumImpact();
        onPressed?.call();
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: backgroundColor ?? CupertinoColors.white,
              shape: BoxShape.circle,
              border: isPrimary ? null : Border.all(color: _AppColors.gray100),
              boxShadow: isPrimary
                  ? [
                      BoxShadow(
                        color: (backgroundColor ?? _AppColors.primary)
                            .withValues(alpha: 0.3),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ]
                  : [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.03),
                        blurRadius: 4,
                        offset: const Offset(0, 2),
                      ),
                    ],
            ),
            child: Icon(
              icon,
              size: isPrimary ? 26 : 28,
              color: isPrimary ? CupertinoColors.white : _AppColors.gray400,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 11,
              fontWeight: isPrimary ? FontWeight.w600 : FontWeight.w500,
              letterSpacing: -0.2,
              color: textColor ?? _AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}
