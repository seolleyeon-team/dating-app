// =============================================================================
// AI 취향 학습 화면 (스와이프 카드 스택)
// 경로: lib/features/ai/screens/ai_taste_training_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/ai/screens/ai_taste_training_screen.dart';
// ...
// home: const AiTasteTrainingScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5E8A);
  static const Color secondary = Color(0xFF8B5CF6);
  static const Color backgroundLight = Color(0xFFFFF7FA);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color yellow400 = Color(0xFFFBBF24);
}

// =============================================================================
// 프로필 모델
// =============================================================================
class _ProfileData {
  final String name;
  final int age;
  final String major;
  final String year;
  final int matchPercent;
  final List<String> tags;
  final String imageUrl;

  const _ProfileData({
    required this.name,
    required this.age,
    required this.major,
    required this.year,
    required this.matchPercent,
    required this.tags,
    required this.imageUrl,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class AiTasteTrainingScreen extends StatefulWidget {
  const AiTasteTrainingScreen({super.key});

  @override
  State<AiTasteTrainingScreen> createState() => _AiTasteTrainingScreenState();
}

class _AiTasteTrainingScreenState extends State<AiTasteTrainingScreen>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;

  final _ProfileData _currentProfile = const _ProfileData(
    name: 'Ji-min',
    age: 24,
    major: 'Business Admin',
    year: "'01",
    matchPercent: 94,
    tags: ['TRAVEL', 'COFFEE'],
    imageUrl:
        'https://lh3.googleusercontent.com/aida-public/AB6AXuBpQ1A8IkjCqwFWBif1GfApoY6AbcZOeKe-Y6cftHlWv1wtjBINpkHdyT4_VlWzi-eGXnzorU1UX8dxB36HeAG3MsYwYfPqGpyWU7HOTqgS-ixtl1IuXUdTyxwGjrMw8FaGmcFQnpnOnB5wtzy40D_TLChaQpLxmoJK3E11WkRuwwMnGaqIOnEcfHEOnibAnhguYt67e-yM8t-ZPkJxS8lziNQBKwnyhIWTKGIX3koUc1D6OefMoPeE3WpzAGrlVRRTN0XyUe3vFZE',
  );

  final int _dailyLimit = 30;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 상단 그라데이션
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: 256,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.primary.withValues(alpha: 0.1),
                    _AppColors.backgroundLight.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                const _Header(),
                // 콘텐츠
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 16),
                        // 타이틀
                        const _TitleSection(),
                        const SizedBox(height: 24),
                        // 카드 스택
                        Expanded(
                          child: _CardStack(
                            profile: _currentProfile,
                            pulseController: _pulseController,
                          ),
                        ),
                        // 데일리 리밋
                        _DailyLimitBadge(limit: _dailyLimit),
                        const SizedBox(height: 100),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 탭바
          const Positioned(
            left: 24,
            right: 24,
            bottom: 24,
            child: _BottomNavBar(),
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
  const _Header();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 로고
          const Row(
            children: [
              Icon(
                CupertinoIcons.heart_fill,
                color: _AppColors.primary,
                size: 22,
              ),
              SizedBox(width: 8),
              Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.5,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          // 우측 버튼
          Row(
            children: [
              // AI 취향 버튼
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFFFCE7F3), Color(0xFFF3E8FF)],
                  ),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  children: [
                    Icon(
                      CupertinoIcons.sparkles,
                      size: 12,
                      color: _AppColors.primary,
                    ),
                    SizedBox(width: 6),
                    Text(
                      'AI 취향',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: _AppColors.textMain,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              // 알림
              Stack(
                children: [
                  const Icon(
                    CupertinoIcons.bell,
                    size: 28,
                    color: _AppColors.gray400,
                  ),
                  Positioned(
                    top: 2,
                    right: 2,
                    child: Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: CupertinoColors.systemRed,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: _AppColors.backgroundLight,
                          width: 2,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // AI Training 배지
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: _AppColors.secondary.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Text(
            'AI TRAINING',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 1,
              color: _AppColors.secondary,
            ),
          ),
        ),
        const SizedBox(height: 12),
        // 타이틀
        const Text(
          '스와이프할수록\n추천이 더 정교해져요',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.3,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(height: 8),
        // 서브타이틀
        const Text(
          'AI 이미지 스와이프로 당신의 취향을 학습합니다.',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 카드 스택
// =============================================================================
class _CardStack extends StatelessWidget {
  final _ProfileData profile;
  final AnimationController pulseController;

  const _CardStack({required this.profile, required this.pulseController});

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        // 백그라운드 카드
        Transform(
          transform: Matrix4.diagonal3Values(0.95, 0.95, 1.0)
            ..setTranslationRaw(0.0, 16.0, 0.0),
          alignment: Alignment.center,
          child: Container(
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(28),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.1),
                  blurRadius: 20,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(28),
              child: ColorFiltered(
                colorFilter: const ColorFilter.mode(
                  CupertinoColors.systemGrey,
                  BlendMode.saturation,
                ),
                child: Opacity(
                  opacity: 0.5,
                  child: Image.network(
                    profile.imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        Container(color: _AppColors.gray100),
                  ),
                ),
              ),
            ),
          ),
        ),
        // 패스 오버레이
        Transform(
          transform: Matrix4.identity()..rotateZ(-0.1),
          alignment: Alignment.center,
          child: Transform.translate(
            offset: const Offset(-48, 0),
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(28),
                border: Border.all(
                  color: _AppColors.gray400.withValues(alpha: 0.3),
                  width: 2,
                ),
              ),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: CupertinoColors.white.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: _AppColors.gray400.withValues(alpha: 0.3),
                    ),
                  ),
                  child: const Text(
                    'PASS',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 24,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 4,
                      color: _AppColors.textSecondary,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
        // 메인 카드
        Transform(
          transform: Matrix4.identity()..rotateZ(0.05),
          alignment: Alignment.center,
          child: Transform.translate(
            offset: const Offset(24, 0),
            child: _ProfileCard(
              profile: profile,
              pulseController: pulseController,
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 프로필 카드
// =============================================================================
class _ProfileCard extends StatelessWidget {
  final _ProfileData profile;
  final AnimationController pulseController;

  const _ProfileCard({required this.profile, required this.pulseController});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.2),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: Stack(
          children: [
            // 이미지
            Positioned.fill(
              child: Image.network(
                profile.imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    Container(color: _AppColors.gray100),
              ),
            ),
            // 그라데이션
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      CupertinoColors.black.withValues(alpha: 0),
                      CupertinoColors.black.withValues(alpha: 0.2),
                      CupertinoColors.black.withValues(alpha: 0.8),
                    ],
                    stops: const [0.0, 0.5, 1.0],
                  ),
                ),
              ),
            ),
            // Like 라벨
            Positioned(
              top: 40,
              left: 32,
              child: Transform.rotate(
                angle: -0.2,
                child: AnimatedBuilder(
                  animation: pulseController,
                  builder: (_, child) {
                    return Opacity(
                      opacity: 0.7 + (0.3 * pulseController.value),
                      child: child,
                    );
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: _AppColors.primary.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: _AppColors.primary.withValues(alpha: 0.4),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: _AppColors.primary.withValues(alpha: 0.3),
                          blurRadius: 15,
                        ),
                      ],
                    ),
                    child: const Text(
                      'LIKE',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 4,
                        color: _AppColors.primary,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            // 프로필 정보
            Positioned(
              left: 24,
              right: 24,
              bottom: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 이름 & 매치율
                  Row(
                    children: [
                      Text(
                        profile.name,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                          color: CupertinoColors.white,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: CupertinoColors.white.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: CupertinoColors.white.withValues(alpha: 0.3),
                          ),
                        ),
                        child: Text(
                          '${profile.matchPercent}% Match',
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // 전공 & 학번
                  Text(
                    '${profile.major} • ${profile.year}',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: CupertinoColors.white.withValues(alpha: 0.8),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // 태그
                  Wrap(
                    spacing: 8,
                    children: profile.tags.map((tag) {
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: CupertinoColors.black.withValues(alpha: 0.4),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: CupertinoColors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        child: Text(
                          tag,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                            color: CupertinoColors.white,
                          ),
                        ),
                      );
                    }).toList(),
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
// 데일리 리밋 배지
// =============================================================================
class _DailyLimitBadge extends StatelessWidget {
  final int limit;

  const _DailyLimitBadge({required this.limit});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _AppColors.gray100),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              CupertinoIcons.bolt_fill,
              size: 14,
              color: _AppColors.yellow400,
            ),
            const SizedBox(width: 8),
            Text(
              'Daily limit: ',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.textSecondary,
              ),
            ),
            Text(
              '$limit',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 네비게이션
// =============================================================================
class _BottomNavBar extends StatelessWidget {
  const _BottomNavBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.08),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
        border: Border.all(color: _AppColors.gray50),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _NavItem(
            icon: CupertinoIcons.heart_fill,
            label: '설레연',
            isActive: true,
          ),
          _NavItem(
            icon: CupertinoIcons.chat_bubble_fill,
            label: '채팅',
            isActive: false,
          ),
          _NavItem(
            icon: CupertinoIcons.calendar,
            label: '이벤트',
            isActive: false,
          ),
          _NavItem(icon: CupertinoIcons.tree, label: '대나무숲', isActive: false),
          _NavItem(
            icon: CupertinoIcons.person_fill,
            label: '내 페이지',
            isActive: false,
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          icon,
          size: 22,
          color: isActive ? _AppColors.primary : _AppColors.gray400,
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 10,
            fontWeight: FontWeight.w500,
            color: isActive ? _AppColors.primary : _AppColors.gray400,
          ),
        ),
      ],
    );
  }
}
