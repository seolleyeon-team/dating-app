import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../data/models/event/event_team_match_model.dart';
import '../../../data/models/event/team_meeting_request_model.dart';
import '../../../router/route_names.dart';
import '../../../services/event_match_service.dart';
import '../../../services/team_meeting_request_service.dart';
import '../models/event_team_route_args.dart';

class MatchResultScreen extends StatefulWidget {
  final EventMatchResultArgs? args;

  const MatchResultScreen({super.key, this.args});

  @override
  State<MatchResultScreen> createState() => _MatchResultScreenState();
}

class _MatchResultScreenState extends State<MatchResultScreen> {
  final EventMatchService _eventMatchService = EventMatchService();
  final TeamMeetingRequestService _requestService =
      TeamMeetingRequestService();

  EventTeamMatchResult? _result;
  String? _viewerGroupId;
  bool _loading = true;
  String? _errorMessage;

  // 팀 요청 관련 상태
  MatchResultEntryMode get _entryMode =>
      widget.args?.entryMode ?? MatchResultEntryMode.slotResult;
  TeamMeetingRequestDoc? _requestDoc;
  StreamSubscription<TeamMeetingRequestDoc?>? _requestSub;
  bool _actionInProgress = false;

  @override
  void initState() {
    super.initState();
    _result = widget.args?.initialResult;
    _viewerGroupId = widget.args?.viewerGroupId;
    _requestDoc = widget.args?.requestDoc;
    _bootstrap();
  }

  @override
  void dispose() {
    _requestSub?.cancel();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final resultId = widget.args?.resultId;

    // 요청 문서 실시간 감시 (요청 리스트에서 진입한 경우)
    final requestId = widget.args?.requestId;
    if (requestId != null && requestId.isNotEmpty) {
      _requestSub = _requestService.watchRequest(requestId).listen((doc) {
        if (!mounted) return;
        setState(() => _requestDoc = doc);
      });
    }

    if (resultId == null || resultId.isEmpty) {
      // 요청 리스트에서 진입 시 resultId 없을 수 있음 — requestDoc의 snapshot 으로 렌더
      if (mounted) {
        setState(() => _loading = false);
      }
      return;
    }

    try {
      final resolvedViewerGroupId = _viewerGroupId ??
          await _eventMatchService.resolveCurrentGroupId(
            preferredTeamSetupId:
                widget.args?.initialResult?.requestingEventTeamSetupId,
          );
      final freshResult =
          await _eventMatchService.getMatchResultOnce(resultId);

      if (!mounted) return;
      setState(() {
        _viewerGroupId = resolvedViewerGroupId;
        _result = freshResult ?? _result;
        _loading = false;
        if (_result == null && _requestDoc == null) {
          _errorMessage = '매칭 결과 문서를 찾지 못했어요.';
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorMessage = '매칭 결과를 다시 불러오는 중 문제가 생겼어요.';
      });
    }
  }

  // ===========================================================================
  // Footer 액션 핸들러
  // ===========================================================================

  Future<void> _sendMeetingRequest() async {
    if (_actionInProgress) return;
    final result = _result;
    if (result == null || _viewerGroupId == null) return;

    setState(() => _actionInProgress = true);
    try {
      await _requestService.createMeetingRequest(
        matchResult: result,
        viewerGroupId: _viewerGroupId!,
      );
      if (!mounted) return;
      _showAlert('미팅 요청을 보냈어요!', onDismiss: () {
        Navigator.of(context).pop();
      });
    } catch (e) {
      if (!mounted) return;
      _showAlert(e.toString().replaceFirst('StateError: ', ''));
    } finally {
      if (mounted) setState(() => _actionInProgress = false);
    }
  }

  Future<void> _acceptRequest() async {
    if (_actionInProgress) return;
    final reqId = _requestDoc?.requestId ?? widget.args?.requestId;
    if (reqId == null) return;

    setState(() => _actionInProgress = true);
    try {
      final matchId = await _requestService.acceptRequest(reqId);
      if (!mounted) return;
      // 수락 성공 → 3:3 매치 화면으로 이동
      Navigator.of(context).pushReplacementNamed(
        RouteNames.threeVsThreeMatch,
        arguments: ThreeVsThreeMatchArgs(matchId: matchId),
      );
    } catch (e) {
      if (!mounted) return;
      _showAlert(e.toString().replaceFirst('StateError: ', ''));
    } finally {
      if (mounted) setState(() => _actionInProgress = false);
    }
  }

  Future<void> _declineRequest() async {
    if (_actionInProgress) return;
    final reqId = _requestDoc?.requestId ?? widget.args?.requestId;
    if (reqId == null) return;

    // 확인 dialog
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        content: const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text('이 요청을 정말 거절하시겠어요?'),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('거절하기'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _actionInProgress = true);
    try {
      await _requestService.declineRequest(reqId);
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      _showAlert(e.toString().replaceFirst('StateError: ', ''));
    } finally {
      if (mounted) setState(() => _actionInProgress = false);
    }
  }

  void _showAlert(String message, {VoidCallback? onDismiss}) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(message),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () {
              Navigator.of(ctx).pop();
              onDismiss?.call();
            },
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // 화면에 표시할 상대 팀 snapshot 결정
  // ===========================================================================

  EventTeamMatchTeamSnapshot? _resolveCounterpart() {
    // 결과 doc 기반
    if (_result != null) {
      return _result!.counterpartForGroup(_viewerGroupId);
    }
    // 요청 doc 기반 (resultId 없이 진입)
    if (_requestDoc != null && _viewerGroupId != null) {
      return _requestDoc!.counterpartSnapshotFor(_viewerGroupId!);
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final counterpart = _resolveCounterpart();
    final requestStatus = _requestDoc?.status;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFF7F3F8),
      child: SafeArea(
        child: Stack(
          children: [
            Column(
              children: [
                _Header(onBackPressed: () => Navigator.of(context).pop()),
                Expanded(
                  child: _loading
                      ? const Center(
                          child: CupertinoActivityIndicator(radius: 16))
                      : counterpart == null
                          ? _EmptyState(
                              message:
                                  _errorMessage ?? '매칭 결과가 아직 없어요.',
                            )
                          : SingleChildScrollView(
                              physics: const BouncingScrollPhysics(),
                              padding:
                                  const EdgeInsets.fromLTRB(20, 8, 20, 140),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  _ResultHero(
                                    team: counterpart,
                                    matchedPairs: _result?.matchedPairs ??
                                        const <Map<String, dynamic>>[],
                                    requestingTeam: _result?.requestingTeam,
                                    matchedTeam: _result?.matchedTeam,
                                  ),
                                  const SizedBox(height: 20),
                                  ...counterpart.members.map(
                                    (member) => Padding(
                                      padding:
                                          const EdgeInsets.only(bottom: 14),
                                      child: _MemberCard(member: member),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                ),
              ],
            ),
            // Footer CTA — mode별 분기
            Positioned(
              left: 20,
              right: 20,
              bottom: 20 + MediaQuery.of(context).padding.bottom,
              child: _buildFooter(requestStatus),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFooter(TeamMeetingRequestStatus? requestStatus) {
    switch (_entryMode) {
      case MatchResultEntryMode.slotResult:
        return _GradientButton(
          label: '팀 전체에게 미팅 요청 보내기',
          onPressed: _sendMeetingRequest,
          isLoading: _actionInProgress,
        );

      case MatchResultEntryMode.receivedTeamRequest:
        // 이미 처리된 요청이면 read-only
        if (requestStatus == TeamMeetingRequestStatus.accepted) {
          return _GradientButton(
            label: '매칭 결과 보기',
            onPressed: () {
              final matchId = _requestDoc?.matchId;
              if (matchId != null && matchId.isNotEmpty) {
                Navigator.of(context).pushNamed(
                  RouteNames.threeVsThreeMatch,
                  arguments: ThreeVsThreeMatchArgs(matchId: matchId),
                );
              }
            },
          );
        }
        if (requestStatus == TeamMeetingRequestStatus.declined) {
          return _ReadOnlyFooter(label: '거절된 요청이에요');
        }
        // pending
        return _AcceptDeclineFooter(
          onAccept: _acceptRequest,
          onDecline: _declineRequest,
          isLoading: _actionInProgress,
        );

      case MatchResultEntryMode.sentTeamRequest:
        if (requestStatus == TeamMeetingRequestStatus.accepted) {
          return _GradientButton(
            label: '매칭 결과 보기',
            onPressed: () {
              final matchId = _requestDoc?.matchId;
              if (matchId != null && matchId.isNotEmpty) {
                Navigator.of(context).pushNamed(
                  RouteNames.threeVsThreeMatch,
                  arguments: ThreeVsThreeMatchArgs(matchId: matchId),
                );
              }
            },
          );
        }
        if (requestStatus == TeamMeetingRequestStatus.declined) {
          return _ReadOnlyFooter(label: '거절된 요청이에요');
        }
        return _ReadOnlyFooter(label: '응답 대기 중이에요');
    }
  }
}

// =============================================================================
// Footer 위젯들
// =============================================================================

class _GradientButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;

  const _GradientButton({
    required this.label,
    this.onPressed,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: isLoading ? null : () {
        HapticFeedback.lightImpact();
        onPressed?.call();
      },
      child: Container(
        height: 56,
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
          borderRadius: BorderRadius.circular(18),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF9B59B6).withValues(alpha: 0.2),
              blurRadius: 16,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        alignment: Alignment.center,
        child: isLoading
            ? const CupertinoActivityIndicator(color: CupertinoColors.white)
            : Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: CupertinoColors.white,
                ),
              ),
      ),
    );
  }
}

class _AcceptDeclineFooter extends StatelessWidget {
  final VoidCallback onAccept;
  final VoidCallback onDecline;
  final bool isLoading;

  const _AcceptDeclineFooter({
    required this.onAccept,
    required this.onDecline,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Primary: 수락
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: isLoading ? null : () {
            HapticFeedback.mediumImpact();
            onAccept();
          },
          child: Container(
            height: 56,
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
              borderRadius: BorderRadius.circular(18),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF9B59B6).withValues(alpha: 0.2),
                  blurRadius: 16,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            alignment: Alignment.center,
            child: isLoading
                ? const CupertinoActivityIndicator(
                    color: CupertinoColors.white)
                : const Text(
                    '요청 수락하기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 10),
        // Secondary: 거절
        CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: isLoading ? null : () {
            HapticFeedback.lightImpact();
            onDecline();
          },
          child: Container(
            height: 48,
            decoration: BoxDecoration(
              color: CupertinoColors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: const Color(0xFFE4D8EF),
              ),
            ),
            alignment: Alignment.center,
            child: const Text(
              '요청 거절하기',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: Color(0xFF776886),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ReadOnlyFooter extends StatelessWidget {
  final String label;

  const _ReadOnlyFooter({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 56,
      decoration: BoxDecoration(
        color: const Color(0xFFEDE3F5),
        borderRadius: BorderRadius.circular(18),
      ),
      alignment: Alignment.center,
      child: Text(
        label,
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Color(0xFF8A7AA0),
        ),
      ),
    );
  }
}

// =============================================================================
// Header (unchanged)
// =============================================================================

class _Header extends StatelessWidget {
  final VoidCallback onBackPressed;

  const _Header({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBackPressed,
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: Color(0xFF2E243F),
                size: 22,
              ),
            ),
          ),
          const Expanded(
            child: Text(
              '매칭 결과',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: Color(0xFF2E243F),
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
// ResultHero (unchanged)
// =============================================================================

class _ResultHero extends StatelessWidget {
  final EventTeamMatchTeamSnapshot team;
  final List<Map<String, dynamic>> matchedPairs;
  final EventTeamMatchTeamSnapshot? requestingTeam;
  final EventTeamMatchTeamSnapshot? matchedTeam;

  const _ResultHero({
    required this.team,
    required this.matchedPairs,
    required this.requestingTeam,
    required this.matchedTeam,
  });

  @override
  Widget build(BuildContext context) {
    final pairLabels = _buildPairLabels();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFFFFFFFF),
            Color(0xFFF3ECF8),
          ],
        ),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
          color: const Color(0xFFE4D8EF),
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF8E74B3).withValues(alpha: 0.10),
            blurRadius: 30,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFFF3E5F5),
              borderRadius: BorderRadius.circular(999),
            ),
            child: const Text(
              '오늘 연결된 팀',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: Color(0xFF8D5AAA),
              ),
            ),
          ),
          const SizedBox(height: 14),
          const Text(
            '룰렛이 멈춘 팀이에요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 26,
              fontWeight: FontWeight.w800,
              color: Color(0xFF2E243F),
              height: 1.25,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${team.memberCount}명의 프로필을 천천히 확인해 보세요.',
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: Color(0xFF776886),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: team.members.take(3).map((member) {
              return Padding(
                padding: const EdgeInsets.only(right: 10),
                child: Column(
                  children: [
                    SizedBox(
                      width: 62,
                      height: 62,
                      child: ClipOval(
                        child: _ProfileImage(photoUrl: member.photoUrl),
                      ),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      width: 64,
                      child: Text(
                        member.displayName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF45375C),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
          if (pairLabels.isNotEmpty) ...[
            const SizedBox(height: 18),
            const Text(
              '추천 페어',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: Color(0xFF5E4E74),
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: pairLabels
                  .map(
                    (label) => Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFFFFF),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: const Color(0xFFE5DCEF),
                        ),
                      ),
                      child: Text(
                        label,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF67557D),
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }

  List<String> _buildPairLabels() {
    if (matchedPairs.isEmpty) return const <String>[];
    final nameByUid = <String, String>{};
    for (final member in requestingTeam?.members ?? const <EventTeamMatchMemberSnapshot>[]) {
      nameByUid[member.uid] = member.displayName;
    }
    for (final member in matchedTeam?.members ?? const <EventTeamMatchMemberSnapshot>[]) {
      nameByUid[member.uid] = member.displayName;
    }

    return matchedPairs.take(3).map((pair) {
      final fromUid = pair['fromUid']?.toString() ?? '';
      final toUid = pair['toUid']?.toString() ?? '';
      final fromName = nameByUid[fromUid] ?? '우리 팀';
      final toName = nameByUid[toUid] ?? '상대 팀';
      return '$fromName ↔ $toName';
    }).toList();
  }
}

// =============================================================================
// MemberCard (unchanged)
// =============================================================================

class _MemberCard extends StatelessWidget {
  final EventTeamMatchMemberSnapshot member;

  const _MemberCard({required this.member});

  @override
  Widget build(BuildContext context) {
    final mannerText = member.mannerScore == null
        ? null
        : '매너 ${member.mannerScore!.toStringAsFixed(1)}';
    final subtitleParts = <String>[
      if (member.universityName?.trim().isNotEmpty == true) member.universityName!,
      if (member.major?.trim().isNotEmpty == true) member.major!,
      if (member.birthYear != null) '${member.birthYear}년생',
    ];

    return Container(
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFFE8DFF0)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF866FA9).withValues(alpha: 0.08),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 88,
              height: 116,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: _ProfileImage(photoUrl: member.photoUrl),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          member.displayName,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF2E243F),
                          ),
                        ),
                      ),
                      if (member.isVerified)
                        const Icon(
                          CupertinoIcons.check_mark_circled_solid,
                          color: Color(0xFF8A5FB2),
                          size: 18,
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  if (subtitleParts.isNotEmpty)
                    Text(
                      subtitleParts.join(' · '),
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF746683),
                      ),
                    ),
                  if (mannerText != null) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF4EBFA),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        mannerText,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF8A5FB2),
                        ),
                      ),
                    ),
                  ],
                  if (member.shortIntro?.trim().isNotEmpty == true) ...[
                    const SizedBox(height: 12),
                    Text(
                      member.shortIntro!,
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        height: 1.45,
                        color: Color(0xFF514665),
                      ),
                    ),
                  ],
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
// ProfileImage / Fallback / EmptyState (unchanged)
// =============================================================================

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
            Color(0xFFF2EAF8),
            Color(0xFFE3D5F0),
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

class _EmptyState extends StatelessWidget {
  final String message;

  const _EmptyState({required this.message});

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
