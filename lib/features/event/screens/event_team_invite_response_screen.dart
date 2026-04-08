import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/event_team_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../models/event_team_route_args.dart';

class _C {
  static const Color primary = Color(0xFFF0426E);
  static const Color bg = Color(0xFFF8F6F6);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF9E9E9E);
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
  final UserService _userService = UserService();
  final StorageService _storage = StorageService();

  String? _meId;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _loadMe();
  }

  Future<void> _loadMe() async {
    final id = await _storage.getKakaoUserId();
    if (mounted) setState(() => _meId = id);
  }

  String _fnError(Object e) {
    if (e is FirebaseFunctionsException) {
      return e.message ?? '요청을 실패했어요.';
    }
    return e.toString();
  }

  String _codeMessage(String code) {
    switch (code) {
      case 'not_found':
        return '초대를 찾을 수 없어요.';
      case 'already_responded':
        return '이미 처리된 초대예요.';
      case 'team_full':
        return '팀 정원이 이미 찼어요. 다음에 다시 만나요.';
      case 'not_friends':
        return '더는 친구 관계가 아니어서 참여할 수 없어요.';
      case 'stale_invite':
        return '유효하지 않은 초대예요.';
      case 'team_missing':
        return '팀 정보가 없어요.';
      default:
        return '초대를 처리하지 못했어요.';
    }
  }

  Future<void> _respond(bool accept) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final res = await _eventTeam.respondInvite(
        inviteId: widget.args.inviteId,
        accept: accept,
      );
      final ok = res['ok'] == true;
      if (!mounted) return;
      if (ok) {
        HapticFeedback.mediumImpact();
        Navigator.of(context).maybePop();
        return;
      }
      final code = res['code']?.toString() ?? '';
      await showCupertinoDialog<void>(
        context: context,
        builder: (ctx) => CupertinoAlertDialog(
          title: const Text('알림'),
          content: Text(_codeMessage(code)),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) {
        await showCupertinoDialog<void>(
          context: context,
          builder: (ctx) => CupertinoAlertDialog(
            title: const Text('오류'),
            content: Text(_fnError(e)),
            actions: [
              CupertinoDialogAction(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('확인'),
              ),
            ],
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _C.bg,
      navigationBar: CupertinoNavigationBar(
        middle: const Text(
          '팀 초대',
          style: TextStyle(fontFamily: 'Pretendard', fontWeight: FontWeight.w700),
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
              return const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    '초대 정보를 찾을 수 없어요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      color: _C.textSub,
                    ),
                  ),
                ),
              );
            }

            final me = _meId;
            if (me != null &&
                me.isNotEmpty &&
                invite.inviteeUserId.isNotEmpty &&
                invite.inviteeUserId != me) {
              return const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    '이 초대는 다른 계정으로 받은 요청이에요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      color: _C.textSub,
                    ),
                  ),
                ),
              );
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
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    msg,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      color: _C.textSub,
                    ),
                  ),
                ),
              );
            }

            return FutureBuilder<String>(
              future: _inviterName(invite.inviterUserId),
              builder: (context, nameSnap) {
                final name = nameSnap.data ?? '친구';
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 32),
                      const Text(
                        '3명 팀 초대',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          color: _C.textMain,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        '$name님이 3인 팀 참여를 요청했어요.\n함께할까요?',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          height: 1.45,
                          color: _C.textSub,
                        ),
                      ),
                      const Spacer(),
                      Row(
                        children: [
                          Expanded(
                            child: CupertinoButton(
                              padding: const EdgeInsets.symmetric(vertical: 14),
                              color: CupertinoColors.systemGrey5,
                              onPressed:
                                  _busy ? null : () => _respond(false),
                              child: const Text(
                                '거절',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontWeight: FontWeight.w700,
                                  color: _C.textMain,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: CupertinoButton(
                              padding: const EdgeInsets.symmetric(vertical: 14),
                              color: _C.primary,
                              onPressed: _busy ? null : () => _respond(true),
                              child: _busy
                                  ? const CupertinoActivityIndicator(
                                      color: CupertinoColors.white,
                                    )
                                  : const Text(
                                      '수락',
                                      style: TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontWeight: FontWeight.w700,
                                        color: CupertinoColors.white,
                                      ),
                                    ),
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 16 + MediaQuery.paddingOf(context).bottom),
                    ],
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  Future<String> _inviterName(String inviterUserId) async {
    if (inviterUserId.isEmpty) return '친구';
    final user = await _userService.getUserProfile(inviterUserId);
    if (user == null) return '친구';
    final raw = user['onboarding'];
    final ob = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    if (ob['nickname']?.toString().trim().isNotEmpty == true) {
      return ob['nickname'].toString();
    }
    if (user['nickname']?.toString().trim().isNotEmpty == true) {
      return user['nickname'].toString();
    }
    return '친구';
  }
}
