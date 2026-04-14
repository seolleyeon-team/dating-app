import 'package:flutter/cupertino.dart';

import '../../../services/event_team_service.dart';
import '../../../services/storage_service.dart';
import '../models/event_team_route_args.dart';
import '../widgets/team_invite_response_sheet.dart';

class _C {
  static const Color bg = Color(0xFFFFFBF7);
  static const Color textMain = Color(0xFF3D2C33);
  static const Color textSub = Color(0xFF89616B);
  static const Color plumAccent = Color(0xFF9B5A6A);
  static const Color plumLight = Color(0xFFF5EBF0);
  static const Color gray200 = Color(0xFFEEEEEE);
}

/// 푸시·알림 목록에서 이벤트 팀 초대에 응답할 때 사용
class EventTeamInviteResponseScreen extends StatefulWidget {
  final EventTeamInviteResponseArgs args;

  const EventTeamInviteResponseScreen({super.key, required this.args});

  @override
  State<EventTeamInviteResponseScreen> createState() =>
      _EventTeamInviteResponseScreenState();
}

class _EventTeamInviteResponseScreenState
    extends State<EventTeamInviteResponseScreen> {
  final EventTeamService _eventTeam = EventTeamService();
  final StorageService _storage = StorageService();

  String? _meId;
  bool _sheetShown = false;

  @override
  void initState() {
    super.initState();
    _loadMe();
  }

  Future<void> _loadMe() async {
    final id = await _storage.getKakaoUserId();
    if (mounted) setState(() => _meId = id);
  }

  /// 초대 문서가 로드되면 자동으로 bottom sheet를 열기
  void _autoShowSheet(EventTeamInviteDoc invite) {
    if (_sheetShown) return;
    _sheetShown = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      showTeamInviteResponseSheet(context, invite: invite).then((_) {
        if (mounted) Navigator.of(context).maybePop();
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _C.bg,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _C.bg,
        border: const Border(),
        middle: const Text(
          '팀 초대',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _C.textMain,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).maybePop(),
          child: const Icon(CupertinoIcons.back, color: _C.textMain),
        ),
      ),
      child: SafeArea(
        child: StreamBuilder<EventTeamInviteDoc?>(
          stream: _eventTeam.watchInvite(widget.args.inviteId),
          builder: (context, snap) {
            final invite = snap.data;
            if (snap.connectionState == ConnectionState.waiting &&
                invite == null) {
              return const Center(child: CupertinoActivityIndicator());
            }
            if (invite == null) {
              return _buildMessage('초대 정보를 찾을 수 없어요.');
            }

            final me = _meId;
            if (me != null &&
                me.isNotEmpty &&
                invite.inviteeUserId.isNotEmpty &&
                invite.inviteeUserId != me) {
              return _buildMessage('이 초대는 다른 계정으로 받은 요청이에요.');
            }

            final status = invite.status.toLowerCase();
            if (status != 'pending') {
              String msg;
              if (status == 'accepted') {
                msg = '이미 수락한 초대예요.';
              } else if (status == 'declined') {
                msg = '거절한 초대예요.';
              } else {
                msg = '더 이상 유효하지 않은 초대예요.';
              }
              return _buildMessage(msg);
            }

            // pending 상태면 bottom sheet 자동 열기
            _autoShowSheet(invite);

            return _buildLoadingState();
          },
        ),
      ),
    );
  }

  Widget _buildMessage(String msg) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: _C.plumLight,
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.mail,
                size: 28,
                color: _C.plumAccent,
              ),
            ),
            const SizedBox(height: 20),
            Text(
              msg,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                fontWeight: FontWeight.w500,
                color: _C.textSub,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 24),
            CupertinoButton(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              color: _C.gray200,
              onPressed: () => Navigator.of(context).maybePop(),
              child: const Text(
                '돌아가기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontWeight: FontWeight.w600,
                  color: _C.textMain,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CupertinoActivityIndicator(),
          const SizedBox(height: 16),
          const Text(
            '초대 내용을 확인하고 있어요…',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: _C.textSub,
            ),
          ),
        ],
      ),
    );
  }
}
