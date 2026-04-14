// =============================================================================
// 팀 미팅 요청 리스트 화면
// 경로: lib/features/event/screens/team_requests_screen.dart
//
// 상단 2개 세그먼트: "받은 요청" / "보낸 요청"
// sent_hearts_screen.dart 감도 참고, 팀 카드형 UI
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../data/models/event/team_meeting_request_model.dart';
import '../../../router/route_names.dart';
import '../../../services/event_match_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/team_meeting_request_service.dart';
import '../models/event_team_route_args.dart';
import '../widgets/team_request_card.dart';

class _AppColors {
  static const Color primary = Color(0xFFB44AC0);
  static const Color backgroundLight = Color(0xFFF7F3F8);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF2E243F);
  static const Color textSub = Color(0xFF776886);
  static const Color gray400 = Color(0xFF9CA3AF);
}

class TeamRequestsScreen extends StatefulWidget {
  const TeamRequestsScreen({super.key});

  @override
  State<TeamRequestsScreen> createState() => _TeamRequestsScreenState();
}

class _TeamRequestsScreenState extends State<TeamRequestsScreen> {
  final TeamMeetingRequestService _service = TeamMeetingRequestService();
  final EventMatchService _matchService = EventMatchService();
  final StorageService _storage = StorageService();

  String? _currentTeamId;
  String? _currentUserId;
  bool _loading = true;
  int _selectedTab = 0; // 0 = 받은 요청, 1 = 보낸 요청

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final uid = await _storage.getKakaoUserId();
    final teamId = await _service.resolveCurrentTeamId();
    if (!mounted) return;
    setState(() {
      _currentUserId = uid;
      _currentTeamId = teamId;
      _loading = false;
    });
  }

  void _onCardTap(TeamMeetingRequestDoc request) {
    final isSent = request.fromTeamId == _currentTeamId;
    final entryMode = isSent
        ? MatchResultEntryMode.sentTeamRequest
        : MatchResultEntryMode.receivedTeamRequest;

    // 이미 accepted 상태이고 matchId가 있으면 3:3 매치 화면으로 직접 이동
    if (request.status == TeamMeetingRequestStatus.accepted &&
        request.matchId != null &&
        request.matchId!.isNotEmpty) {
      Navigator.of(context).pushNamed(
        RouteNames.threeVsThreeMatch,
        arguments: ThreeVsThreeMatchArgs(matchId: request.matchId!),
      );
      return;
    }

    Navigator.of(context).pushNamed(
      RouteNames.matchResult,
      arguments: EventMatchResultArgs(
        resultId: request.sourceResultId ?? '',
        viewerGroupId: _currentTeamId,
        entryMode: entryMode,
        requestId: request.requestId,
        requestDoc: request,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        child: Column(
          children: [
            _Header(onBack: () => Navigator.of(context).pop()),
            const SizedBox(height: 12),
            _SegmentControl(
              selectedIndex: _selectedTab,
              onChanged: (index) => setState(() => _selectedTab = index),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: _loading
                  ? const Center(child: CupertinoActivityIndicator(radius: 14))
                  : _currentTeamId == null
                      ? const _EmptyState(
                          icon: CupertinoIcons.person_3,
                          message: '아직 팀이 구성되지 않았어요.\n팀을 완성하면 요청을 확인할 수 있어요.',
                        )
                      : _selectedTab == 0
                          ? _RequestList(
                              stream: _service
                                  .watchReceivedRequests(_currentTeamId!),
                              currentTeamId: _currentTeamId!,
                              onCardTap: _onCardTap,
                              emptyIcon: CupertinoIcons.tray,
                              emptyMessage: '받은 요청이 아직 없어요.\n상대 팀의 요청이 오면 여기에 표시돼요.',
                            )
                          : _RequestList(
                              stream:
                                  _service.watchSentRequests(_currentTeamId!),
                              currentTeamId: _currentTeamId!,
                              onCardTap: _onCardTap,
                              emptyIcon: CupertinoIcons.paperplane,
                              emptyMessage:
                                  '보낸 요청이 아직 없어요.\n슬롯 결과에서 팀에 요청을 보내보세요.',
                            ),
            ),
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
  final VoidCallback onBack;

  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: () {
              HapticFeedback.lightImpact();
              onBack();
            },
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 22,
              ),
            ),
          ),
          const Expanded(
            child: Text(
              '팀 미팅 요청',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
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
// 세그먼트 컨트롤
// =============================================================================

class _SegmentControl extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  const _SegmentControl({
    required this.selectedIndex,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Container(
        height: 44,
        decoration: BoxDecoration(
          color: CupertinoColors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: _AppColors.primary.withValues(alpha: 0.08),
          ),
        ),
        child: Row(
          children: [
            _SegmentTab(
              label: '받은 요청',
              isSelected: selectedIndex == 0,
              onTap: () => onChanged(0),
            ),
            _SegmentTab(
              label: '보낸 요청',
              isSelected: selectedIndex == 1,
              onTap: () => onChanged(1),
            ),
          ],
        ),
      ),
    );
  }
}

class _SegmentTab extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _SegmentTab({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          margin: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: isSelected
                ? _AppColors.primary.withValues(alpha: 0.1)
                : CupertinoColors.white.withValues(alpha: 0),
            borderRadius: BorderRadius.circular(10),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
              color: isSelected ? _AppColors.primary : _AppColors.textSub,
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 요청 리스트 (StreamBuilder)
// =============================================================================

class _RequestList extends StatelessWidget {
  final Stream<List<TeamMeetingRequestDoc>> stream;
  final String currentTeamId;
  final void Function(TeamMeetingRequestDoc) onCardTap;
  final IconData emptyIcon;
  final String emptyMessage;

  const _RequestList({
    required this.stream,
    required this.currentTeamId,
    required this.onCardTap,
    required this.emptyIcon,
    required this.emptyMessage,
  });

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<List<TeamMeetingRequestDoc>>(
      stream: stream,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CupertinoActivityIndicator(radius: 14));
        }
        if (snapshot.hasError) {
          return Center(
            child: Text(
              '데이터를 불러올 수 없어요',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                color: _AppColors.gray400,
              ),
            ),
          );
        }

        final items = snapshot.data ?? [];

        // pending 우선 노출
        final sorted = List<TeamMeetingRequestDoc>.from(items)
          ..sort((a, b) {
            if (a.isPending && !b.isPending) return -1;
            if (!a.isPending && b.isPending) return 1;
            final cA = a.createdAt?.millisecondsSinceEpoch ?? 0;
            final cB = b.createdAt?.millisecondsSinceEpoch ?? 0;
            return cB.compareTo(cA);
          });

        if (sorted.isEmpty) {
          return _EmptyState(icon: emptyIcon, message: emptyMessage);
        }

        return ListView.separated(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          itemCount: sorted.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, index) {
            return TeamRequestCard(
              request: sorted[index],
              currentTeamId: currentTeamId,
              onTap: () => onCardTap(sorted[index]),
            );
          },
        );
      },
    );
  }
}

// =============================================================================
// Empty State
// =============================================================================

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;

  const _EmptyState({required this.icon, required this.message});

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
                color: _AppColors.primary.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Icon(
                icon,
                color: _AppColors.primary.withValues(alpha: 0.35),
                size: 34,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                fontWeight: FontWeight.w500,
                height: 1.55,
                color: _AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
