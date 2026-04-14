import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../data/models/event/event_team_match_model.dart';
import '../../../router/route_names.dart';
import '../../../services/event_match_service.dart';
import '../models/event_team_route_args.dart';
import '../widgets/event_slot_machine.dart';
import '../widgets/slot_reel_controller.dart';

class SeasonMeetingRouletteScreen extends StatefulWidget {
  final SeasonMeetingRouletteArgs? args;
  final VoidCallback? onBack;
  final VoidCallback? onSpin;
  final int ticketCount;

  const SeasonMeetingRouletteScreen({
    super.key,
    this.args,
    this.onBack,
    this.onSpin,
    this.ticketCount = 5,
  });

  @override
  State<SeasonMeetingRouletteScreen> createState() =>
      _SeasonMeetingRouletteScreenState();
}

class _SeasonMeetingRouletteScreenState
    extends State<SeasonMeetingRouletteScreen> {
  final _reel1 = SlotReelController();
  final _reel2 = SlotReelController();
  final _reel3 = SlotReelController();
  final EventMatchService _eventMatchService = EventMatchService();

  List<EventTeamMatchTeamSnapshot> _candidateTeams =
      const <EventTeamMatchTeamSnapshot>[];
  bool _resolvingSpin = false;
  bool _spinning = false;
  String? _statusMessage;
  String? _errorMessage;

  List<Widget> _buildReelItems(int memberIndex) {
    if (_candidateTeams.isEmpty) {
      return List<Widget>.generate(
        4,
        (_) => const _PlaceholderSlotProfileCard(),
      );
    }
    return _candidateTeams
        .map(
          (team) => _SlotProfileCard(
            member: team.members.length > memberIndex
                ? team.members[memberIndex]
                : const EventTeamMatchMemberSnapshot(
                    uid: '',
                    displayName: '프로필 준비 중',
                  ),
          ),
        )
        .toList();
  }

  Future<void> _spin() async {
    if (_resolvingSpin || _spinning) return;

    setState(() {
      _resolvingSpin = true;
      _errorMessage = null;
      _statusMessage = '추천 팀을 찾고 있어요...';
    });
    widget.onSpin?.call();

    try {
      final response = await _eventMatchService.spinSeasonMeetingRoulette(
        teamSetupId: widget.args?.teamSetupId ?? '',
      );
      if (!mounted) return;

      if (response.reusedExisting) {
        setState(() {
          _resolvingSpin = false;
          _statusMessage = '이미 확정된 결과를 열고 있어요.';
        });
        _navigateToResult(response);
        return;
      }

      if (response.result.candidateTeams.isEmpty) {
        throw StateError('추천 후보 팀이 비어 있어요.');
      }

      setState(() {
        _candidateTeams = response.result.candidateTeams;
        _resolvingSpin = false;
        _spinning = true;
        _statusMessage = '추천 결과에 맞춰 릴을 돌리고 있어요...';
      });

      await Future<void>.delayed(const Duration(milliseconds: 80));
      final targetIndex = response.selectedTeamIndex;

      await Future.wait([
        _reel1.spinTo(
          targetIndex,
          duration: const Duration(milliseconds: 1400),
          extraTurns: 4,
        ),
        () async {
          await Future<void>.delayed(const Duration(milliseconds: 120));
          await _reel2.spinTo(
            targetIndex,
            duration: const Duration(milliseconds: 1700),
            extraTurns: 5,
          );
        }(),
        () async {
          await Future<void>.delayed(const Duration(milliseconds: 240));
          await _reel3.spinTo(
            targetIndex,
            duration: const Duration(milliseconds: 2000),
            extraTurns: 6,
          );
        }(),
      ]);

      if (!mounted) return;
      setState(() {
        _spinning = false;
        _statusMessage = null;
      });
      _navigateToResult(response);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _resolvingSpin = false;
        _spinning = false;
        _statusMessage = null;
        _errorMessage = _readErrorMessage(error);
      });
    }
  }

  void _navigateToResult(EventTeamMatchSpinResponse response) {
    Navigator.of(context).pushNamed(
      RouteNames.matchResult,
      arguments: EventMatchResultArgs(
        resultId: response.result.resultId,
        initialResult: response.result,
        viewerGroupId: response.viewerGroupId,
      ),
    );
  }

  String _readErrorMessage(Object error) {
    final message = error.toString();
    if (message.contains('추천 결과가 아직 준비되지 않았어요')) {
      return '추천 결과를 준비 중이에요. 잠시 후 다시 시도해 주세요.';
    }
    if (message.contains('팀이 3명으로 완성되면')) {
      return '팀이 3명으로 완성되면 룰렛을 시작할 수 있어요.';
    }
    if (message.contains('추천 가능한 상대 팀이 없어요')) {
      return '오늘은 아직 연결 가능한 팀이 보이지 않아요.';
    }
    return '지금은 룰렛을 시작할 수 없어요. 잠시 후 다시 시도해 주세요.';
  }

  @override
  Widget build(BuildContext context) {
    final reel1Items = _buildReelItems(0);
    final reel2Items = _buildReelItems(1);
    final reel3Items = _buildReelItems(2);
    final isBusy = _resolvingSpin || _spinning;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFE9E4F0),
      child: Stack(
        children: [
          const _BackgroundGlow(),
          SafeArea(
            child: Column(
              children: [
                _Header(
                  onBack: widget.onBack ?? () => Navigator.of(context).pop(),
                  ticketCount: widget.ticketCount,
                ),
                const _TitleSection(),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
                  child: _StatusBanner(
                    message: _statusMessage,
                    errorMessage: _errorMessage,
                    hasResolvedTeams: _candidateTeams.isNotEmpty,
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 380),
                        child: EventSlotMachine(
                          reel1: _reel1,
                          reel2: _reel2,
                          reel3: _reel3,
                          reel1Items: reel1Items,
                          reel2Items: reel2Items,
                          reel3Items: reel3Items,
                          onLeverPull: _spin,
                          spinning: isBusy,
                        ),
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 36),
                  child: _SpinButton(
                    onPressed: _spin,
                    spinning: isBusy,
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

class _BackgroundGlow extends StatelessWidget {
  const _BackgroundGlow();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFFD5C8EC), Color(0xFFF1E6F4)],
            ),
          ),
        ),
        Positioned(
          top: -200,
          right: -80,
          child: Container(
            width: 420,
            height: 420,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFE1BEE7).withValues(alpha: 0.35),
            ),
          ),
        ),
        Positioned(
          bottom: -120,
          left: -80,
          child: Container(
            width: 360,
            height: 360,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFFCE4EC).withValues(alpha: 0.3),
            ),
          ),
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  final VoidCallback onBack;
  final int ticketCount;

  const _Header({required this.onBack, required this.ticketCount});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.lightImpact();
              onBack();
            },
            child: ClipRRect(
              borderRadius: BorderRadius.circular(20),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFFFFF).withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: const Color(0xFFFFFFFF).withValues(alpha: 0.4),
                    ),
                  ),
                  child: const Icon(
                    CupertinoIcons.back,
                    size: 20,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
            ),
          ),
          const Text(
            '3:3 시즌 미팅',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1E293B),
            ),
          ),
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFFFFF).withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: const Color(0xFFFFFFFF).withValues(alpha: 0.4),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF000000).withValues(alpha: 0.05),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    const Icon(
                      CupertinoIcons.ticket_fill,
                      size: 18,
                      color: Color(0xFFCE93D8),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '$ticketCount',
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF334155),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        children: [
          Text(
            '추천 팀으로 만나는\n시즌 미팅 룰렛',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 30,
              fontWeight: FontWeight.w800,
              color: const Color(0xFFFFFFFF),
              shadows: [
                Shadow(
                  color: const Color(0xFF000000).withValues(alpha: 0.12),
                  offset: const Offset(0, 2),
                  blurRadius: 6,
                ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '추천 시스템이 고른 상대 팀으로 릴이 함께 멈춰요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: const Color(0xFFFFFFFF).withValues(alpha: 0.82),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final String? message;
  final String? errorMessage;
  final bool hasResolvedTeams;

  const _StatusBanner({
    required this.message,
    required this.errorMessage,
    required this.hasResolvedTeams,
  });

  @override
  Widget build(BuildContext context) {
    final bannerMessage = errorMessage ??
        message ??
        (hasResolvedTeams
            ? '추천된 팀 프로필로 릴이 정렬되어 있어요.'
            : '룰렛을 돌리면 추천 후보 팀의 실제 프로필이 릴에 올라와요.');
    final isError = errorMessage != null;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: (isError
                ? const Color(0xFFF7D7E0)
                : const Color(0xFFFFFFFF))
            .withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: (isError
                  ? const Color(0xFFE87A97)
                  : const Color(0xFFE6DCEF))
              .withValues(alpha: 0.9),
        ),
      ),
      child: Row(
        children: [
          Icon(
            isError ? CupertinoIcons.exclamationmark_circle : CupertinoIcons.sparkles,
            size: 18,
            color: isError ? const Color(0xFFD94C72) : const Color(0xFF8D66B8),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              bannerMessage,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color:
                    isError ? const Color(0xFF8E304C) : const Color(0xFF5A4A71),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SpinButton extends StatelessWidget {
  final VoidCallback onPressed;
  final bool spinning;

  const _SpinButton({
    required this.onPressed,
    required this.spinning,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: spinning
          ? null
          : () {
              HapticFeedback.heavyImpact();
              onPressed();
            },
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 200),
        opacity: spinning ? 0.6 : 1.0,
        child: Stack(
          children: [
            Container(
              width: double.infinity,
              height: 60,
              margin: const EdgeInsets.only(top: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF8E44AD),
                borderRadius: BorderRadius.circular(30),
              ),
            ),
            Container(
              width: double.infinity,
              height: 60,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: [
                    Color(0xFFB44AC0),
                    Color(0xFFD084D8),
                    Color(0xFFE89AD0),
                  ],
                ),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(
                  color: const Color(0xFFFFFFFF).withValues(alpha: 0.25),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF9B59B6).withValues(alpha: 0.3),
                    blurRadius: 16,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Center(
                child: Text(
                  spinning ? '추천 팀을 맞추는 중...' : '추천 룰렛 돌리기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.2,
                    color: CupertinoColors.white,
                    shadows: [
                      Shadow(
                        color: const Color(0xFF000000).withValues(alpha: 0.2),
                        offset: const Offset(0, 1),
                        blurRadius: 2,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SlotProfileCard extends StatelessWidget {
  final EventTeamMatchMemberSnapshot member;

  const _SlotProfileCard({required this.member});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: const LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFFFDFBFF),
              Color(0xFFF3EDF8),
            ],
          ),
          border: Border.all(
            color: const Color(0xFFE1D4EE),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF8A70AF).withValues(alpha: 0.08),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: AspectRatio(
                  aspectRatio: 1,
                  child: _ProfileImage(photoUrl: member.photoUrl),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Flexible(
                    child: Text(
                      member.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF34284A),
                      ),
                    ),
                  ),
                  if (member.isVerified) ...[
                    const SizedBox(width: 4),
                    const Icon(
                      CupertinoIcons.check_mark_circled_solid,
                      size: 14,
                      color: Color(0xFF7C5BA0),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 4),
              Text(
                member.universityName?.trim().isNotEmpty == true
                    ? member.universityName!
                    : '학교 인증 프로필',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF8B7BA4),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlaceholderSlotProfileCard extends StatelessWidget {
  const _PlaceholderSlotProfileCard();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.all(8),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.all(Radius.circular(18)),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFFFDFBFF),
              Color(0xFFF3EDF8),
            ],
          ),
        ),
        child: Center(
          child: Icon(
            CupertinoIcons.person_2_fill,
            size: 34,
            color: Color(0xFFC4B4D8),
          ),
        ),
      ),
    );
  }
}

class _ProfileImage extends StatelessWidget {
  final String? photoUrl;

  const _ProfileImage({required this.photoUrl});

  @override
  Widget build(BuildContext context) {
    if (photoUrl == null || photoUrl!.isEmpty) {
      return const _ProfileImageFallback();
    }

    return Image.network(
      photoUrl!,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => const _ProfileImageFallback(),
    );
  }
}

class _ProfileImageFallback extends StatelessWidget {
  const _ProfileImageFallback();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFFF1E8F8),
            Color(0xFFE1D4EE),
          ],
        ),
      ),
      child: const Center(
        child: Icon(
          CupertinoIcons.person_fill,
          size: 34,
          color: Color(0xFFA38ABC),
        ),
      ),
    );
  }
}
