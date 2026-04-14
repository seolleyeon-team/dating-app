// =============================================================================
// 3:3 매칭 결과 화면 (상대 팀 공개 화면)
// 경로: lib/features/event/screens/three_vs_three_match_screen.dart
//
// 실제 match doc (eventThreeVsThreeMatches)에서 양쪽 팀 프로필을 로드.
// 기존 mock 프로필 제거 → 실제 사용자 데이터로 교체.
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;

import '../../../data/models/event/event_team_match_model.dart';
import '../../../data/models/event/team_meeting_match_model.dart';
import '../../../services/storage_service.dart';
import '../../../services/team_meeting_request_service.dart';
import '../models/event_team_route_args.dart';

// =============================================================================
// 색상 정의
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5A78);
  static const Color backgroundLight = Color(0xFFF9FAFB);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF111827);
  static const Color textSub = Color(0xFF6B7280);
  static const Color textGray800 = Color(0xFF1F2937);
}

// =============================================================================
// 메인 화면
// =============================================================================
class ThreeVsThreeMatchScreen extends StatefulWidget {
  final ThreeVsThreeMatchArgs? args;

  const ThreeVsThreeMatchScreen({super.key, this.args});

  @override
  State<ThreeVsThreeMatchScreen> createState() =>
      _ThreeVsThreeMatchScreenState();
}

class _ThreeVsThreeMatchScreenState extends State<ThreeVsThreeMatchScreen> {
  final TeamMeetingRequestService _service = TeamMeetingRequestService();
  final StorageService _storage = StorageService();

  TeamMeetingMatchDoc? _match;
  String? _currentUserId;
  bool _loading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final uid = await _storage.getKakaoUserId();
    final matchId = widget.args?.matchId;

    if (matchId == null || matchId.isEmpty) {
      if (mounted) {
        setState(() {
          _currentUserId = uid;
          _loading = false;
          _errorMessage = '매칭 정보를 불러올 수 없어요.';
        });
      }
      return;
    }

    try {
      final match = await _service.getMatchOnce(matchId);
      if (!mounted) return;
      setState(() {
        _currentUserId = uid;
        _match = match;
        _loading = false;
        if (match == null) {
          _errorMessage = '매칭 문서를 찾지 못했어요.';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _currentUserId = uid;
        _loading = false;
        _errorMessage = '매칭 정보를 불러오는 중 문제가 생겼어요.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final uid = _currentUserId ?? '';
    final myTeam = _match?.myTeamSnapshot(uid);
    final opponentTeam = _match?.opponentTeamSnapshot(uid);

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        bottom: false,
        child: Stack(
          children: [
            Column(
              children: [
                _Header(onBack: () => Navigator.of(context).pop()),
                Expanded(
                  child: _loading
                      ? const Center(
                          child: CupertinoActivityIndicator(radius: 16))
                      : _errorMessage != null
                          ? _ErrorState(message: _errorMessage!)
                          : SingleChildScrollView(
                              physics: const BouncingScrollPhysics(),
                              padding: const EdgeInsets.only(
                                left: 20,
                                right: 20,
                                top: 24,
                                bottom: 100,
                              ),
                              child: Column(
                                children: [
                                  _TeamSection(
                                    title: '상대 팀',
                                    badge: '매칭 완료',
                                    team: opponentTeam,
                                    currentUserId: uid,
                                    gradientSets: _opponentGradients,
                                  ),
                                  const _HeartPulseAnimation(),
                                  _TeamSection(
                                    title: '우리 팀',
                                    team: myTeam,
                                    currentUserId: uid,
                                    gradientSets: _myTeamGradients,
                                    isMyTeam: true,
                                  ),
                                  const SizedBox(height: 80),
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
              child: const _BottomActionBar(),
            ),
          ],
        ),
      ),
    );
  }
}

// 그라데이션 세트 (상대 팀)
const List<List<Color>> _opponentGradients = [
  [Color(0xFFDBEAFE), Color(0xFFBFDBFE)],
  [Color(0xFFF3E8FF), Color(0xFFE9D5FF)],
  [Color(0xFFE0E7FF), Color(0xFFC7D2FE)],
];

// 그라데이션 세트 (내 팀)
const List<List<Color>> _myTeamGradients = [
  [Color(0xFFFFEDD5), Color(0xFFFEF3C7)],
  [Color(0xFFFEF3C7), Color(0xFFFEE2E2)],
  [Color(0xFFF3F4F6), Color(0xFFE5E7EB)],
];

// =============================================================================
// 팀 섹션
// =============================================================================

class _TeamSection extends StatelessWidget {
  final String title;
  final String? badge;
  final EventTeamMatchTeamSnapshot? team;
  final String currentUserId;
  final List<List<Color>> gradientSets;
  final bool isMyTeam;

  const _TeamSection({
    required this.title,
    this.badge,
    required this.team,
    required this.currentUserId,
    required this.gradientSets,
    this.isMyTeam = false,
  });

  @override
  Widget build(BuildContext context) {
    final members = team?.members ?? const <EventTeamMatchMemberSnapshot>[];

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: _AppColors.textSub,
                  letterSpacing: 0.5,
                ),
              ),
              if (badge != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    badge!,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.primary,
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            for (var i = 0; i < 3; i++) ...[
              if (i > 0) const SizedBox(width: 12),
              Expanded(
                child: i < members.length
                    ? _ProfileCard(
                        member: members[i],
                        gradientColors: gradientSets[i % gradientSets.length],
                        isMe: isMyTeam && members[i].uid == currentUserId,
                      )
                    : _EmptyProfileCard(
                        gradientColors: gradientSets[i % gradientSets.length],
                      ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

// =============================================================================
// 실제 프로필 카드
// =============================================================================

class _ProfileCard extends StatelessWidget {
  final EventTeamMatchMemberSnapshot member;
  final List<Color> gradientColors;
  final bool isMe;

  const _ProfileCard({
    required this.member,
    required this.gradientColors,
    this.isMe = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 3 / 4,
          child: Container(
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(24),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x0A000000),
                  blurRadius: 30,
                  offset: Offset(0, 8),
                ),
              ],
              border: isMe
                  ? Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.2),
                      width: 2,
                    )
                  : null,
            ),
            child: Stack(
              children: [
                // 프로필 사진
                ClipRRect(
                  borderRadius: BorderRadius.circular(isMe ? 22 : 24),
                  child: SizedBox.expand(
                    child: member.photoUrl != null &&
                            member.photoUrl!.isNotEmpty
                        ? Image.network(
                            member.photoUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) =>
                                _FallbackIcon(gradientColors: gradientColors),
                          )
                        : _FallbackIcon(gradientColors: gradientColors),
                  ),
                ),
                // 하단 그라데이션 오버레이 + 이름
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(10, 28, 10, 10),
                    decoration: BoxDecoration(
                      borderRadius: const BorderRadius.only(
                        bottomLeft: Radius.circular(24),
                        bottomRight: Radius.circular(24),
                      ),
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.45),
                        ],
                      ),
                    ),
                    child: Text(
                      member.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                  ),
                ),
                // 인증 뱃지
                if (member.isVerified)
                  Positioned(
                    top: 8,
                    right: 8,
                    child: Container(
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.9),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        CupertinoIcons.check_mark_circled_solid,
                        size: 16,
                        color: Color(0xFF7C5BA0),
                      ),
                    ),
                  ),
                // ME 뱃지
                if (isMe)
                  Positioned(
                    top: 8,
                    left: 8,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: _AppColors.primary,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Text(
                        'ME',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          member.universityName?.trim().isNotEmpty == true
              ? member.universityName!
              : '',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w500,
            color: Color(0xFF9CA3AF),
          ),
        ),
      ],
    );
  }
}

class _FallbackIcon extends StatelessWidget {
  final List<Color> gradientColors;

  const _FallbackIcon({required this.gradientColors});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomLeft,
          end: Alignment.topRight,
          colors: gradientColors,
        ),
      ),
      child: const Center(
        child: Icon(
          CupertinoIcons.person_fill,
          size: 36,
          color: Color(0xFFA38ABC),
        ),
      ),
    );
  }
}

class _EmptyProfileCard extends StatelessWidget {
  final List<Color> gradientColors;

  const _EmptyProfileCard({required this.gradientColors});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 3 / 4,
          child: Container(
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(24),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x0A000000),
                  blurRadius: 30,
                  offset: Offset(0, 8),
                ),
              ],
            ),
            child: _FallbackIcon(gradientColors: gradientColors),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          '',
          style: TextStyle(fontSize: 11),
        ),
      ],
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBack;

  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight.withValues(alpha: 0.8),
        border: const Border(
          bottom: BorderSide(color: Color(0xFFF3F4F6)),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onBack,
            child: const Icon(
              Icons.arrow_back,
              color: Color(0xFF1F2937),
              size: 24,
            ),
          ),
          const Text(
            '설레연 3:3 미팅',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

// =============================================================================
// 중앙 하트 펄스 애니메이션
// =============================================================================
class _HeartPulseAnimation extends StatefulWidget {
  const _HeartPulseAnimation();

  @override
  State<_HeartPulseAnimation> createState() => _HeartPulseAnimationState();
}

class _HeartPulseAnimationState extends State<_HeartPulseAnimation>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: 1.2,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 120,
      alignment: Alignment.center,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 1,
            height: 80,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.transparent,
                  Colors.grey.shade200,
                  Colors.transparent,
                ],
              ),
            ),
          ),
          ScaleTransition(
            scale: _scaleAnimation,
            child: Container(
              width: 48,
              height: 48,
              decoration: const BoxDecoration(
                color: _AppColors.surfaceLight,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: Color(0x0A000000),
                    blurRadius: 30,
                    offset: Offset(0, 8),
                  ),
                ],
              ),
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.grey.shade50),
                ),
                child: const Icon(
                  Icons.favorite,
                  color: _AppColors.primary,
                  size: 24,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// Error State
// =============================================================================

class _ErrorState extends StatelessWidget {
  final String message;

  const _ErrorState({required this.message});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFFEDE3F5),
                borderRadius: BorderRadius.circular(24),
              ),
              child: const Icon(
                CupertinoIcons.person_3_fill,
                color: Color(0xFFA383C1),
                size: 34,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 16,
                fontWeight: FontWeight.w600,
                height: 1.45,
                color: Color(0xFF5C4F6F),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 액션 버튼
// =============================================================================
class _BottomActionBar extends StatelessWidget {
  const _BottomActionBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.white.withValues(alpha: 0), Colors.white],
          stops: const [0.0, 0.3],
        ),
      ),
      padding: EdgeInsets.fromLTRB(
        24,
        48,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () {},
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 20,
                spreadRadius: 0,
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Text(
                '채팅방 입장하기',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
              SizedBox(width: 8),
              Icon(Icons.chat_bubble_rounded, color: Colors.white, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
