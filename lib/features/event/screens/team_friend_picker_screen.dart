import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/auth_service.dart';
import '../../../services/event_team_service.dart';
import '../../../services/friend_service.dart';
import '../../../services/storage_service.dart';
import '../../profile/widgets/friends_list_shared.dart';
import '../models/event_team_route_args.dart';

class _Colors {
  static const Color primary = Color(0xFFF0428B);
  static const Color background = Color(0xFFF8F8FA);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF8B8B94);
  static const Color line = Color(0xFFE9E9EE);
}

/// 이벤트 3인 팀 구성용: 현재 친구만 목록에서 고르고 초대를 보냅니다.
class TeamFriendPickerScreen extends StatefulWidget {
  final TeamFriendPickerArgs args;

  const TeamFriendPickerScreen({super.key, required this.args});

  @override
  State<TeamFriendPickerScreen> createState() => _TeamFriendPickerScreenState();
}

class _TeamFriendPickerScreenState extends State<TeamFriendPickerScreen> {
  final AuthService _authService = AuthService();
  final StorageService _storageService = StorageService();
  final FriendService _friendService = FriendService();
  final EventTeamService _eventTeamService = EventTeamService();

  String? _currentUserId;
  bool _ready = false;
  bool _canReadFriends = false;
  final Set<String> _selected = {};

  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final uid = await _storageService.getKakaoUserId();
    if (uid == null || uid.isEmpty) {
      if (mounted) {
        setState(() {
          _currentUserId = uid;
          _ready = true;
          _canReadFriends = false;
        });
      }
      return;
    }
    final canRead = await _authService.ensureFirebaseSessionForKakao(uid);
    if (!mounted) return;
    setState(() {
      _currentUserId = uid;
      _ready = true;
      _canReadFriends = canRead;
    });
  }

  String _formatAddedAt(DateTime? dateTime) {
    if (dateTime == null) return '추가일 정보 없음';
    final month = dateTime.month.toString().padLeft(2, '0');
    final day = dateTime.day.toString().padLeft(2, '0');
    return '${dateTime.year}.$month.$day 친구가 되었어요';
  }

  int _remainingSlots(EventTeamSetupState state) => state.remainingSlots;

  void _onToggle(FriendListItem item, bool willSelect, int remainingSlots) {
    if (willSelect && remainingSlots <= 0) {
      HapticFeedback.selectionClick();
      return;
    }
    if (willSelect && _selected.length >= remainingSlots) {
      HapticFeedback.selectionClick();
      _toast(
        '함께할 수 있는 자리가 부족해요. (최대 3명, 본인 포함)',
      );
      return;
    }
    HapticFeedback.selectionClick();
    setState(() {
      if (willSelect) {
        _selected.add(item.friendUserId);
      } else {
        _selected.remove(item.friendUserId);
      }
    });
  }

  void _toast(String message) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text('알림'),
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(message),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  String _functionsMessage(Object e) {
    if (e is FirebaseFunctionsException) {
      return e.message ?? '요청을 처리하지 못했어요.';
    }
    return e.toString().replaceFirst('Exception: ', '').replaceFirst(
          'StateError: ',
          '',
        );
  }

  Future<void> _sendInvites() async {
    if (_sending || _selected.isEmpty) return;
    final team = await _eventTeamService.getTeamSetupOnce(
      widget.args.teamSetupId,
    );
    if (team == null) {
      _toast('팀 정보를 불러오지 못했어요.');
      return;
    }
    if (_currentUserId != team.leaderUserId) {
      _toast('팀 리더만 초대할 수 있어요.');
      return;
    }

    setState(() => _sending = true);
    var sent = 0;
    final targets = List<String>.from(_selected);
    try {
      for (final inviteeUserId in targets) {
        await _eventTeamService.createInvite(
          teamSetupId: widget.args.teamSetupId,
          inviteeUserId: inviteeUserId,
        );
        sent++;
        if (mounted) setState(() => _selected.remove(inviteeUserId));
      }
      if (mounted && sent > 0) {
        HapticFeedback.mediumImpact();
        Navigator.of(context).maybePop();
      }
    } catch (e) {
      if (mounted) {
        _toast(_functionsMessage(e));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _Colors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _Colors.surface.withValues(alpha: 0.92),
        border: const Border(
          bottom: BorderSide(color: _Colors.line, width: 0.5),
        ),
        middle: const Text(
          '친구 초대',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _Colors.textMain,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).maybePop();
          },
          child: const Icon(CupertinoIcons.back, color: _Colors.textMain),
        ),
      ),
      child: SafeArea(
        child: !_ready
            ? const Center(child: CupertinoActivityIndicator())
            : _currentUserId == null || _currentUserId!.isEmpty
                ? const Center(
                    child: Text(
                      '로그인이 필요해요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        color: _Colors.textSub,
                      ),
                    ),
                  )
                : !_canReadFriends
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.symmetric(horizontal: 28),
                          child: Text(
                            '학교 이메일 인증이 완료된 계정에서 친구 목록을 열 수 있어요.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 14,
                              height: 1.45,
                              color: _Colors.textSub,
                            ),
                          ),
                        ),
                      )
                    : StreamBuilder<EventTeamSetupState?>(
                        stream: _eventTeamService.watchTeamSetup(
                          widget.args.teamSetupId,
                        ),
                        builder: (context, teamSnap) {
                          final team = teamSnap.data;
                          if (teamSnap.connectionState ==
                                  ConnectionState.waiting &&
                              team == null) {
                            return const Center(
                              child: CupertinoActivityIndicator(),
                            );
                          }
                          if (team == null) {
                            return const Center(
                              child: Text(
                                '팀 정보를 찾을 수 없어요',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  color: _Colors.textSub,
                                ),
                              ),
                            );
                          }
                          if (_currentUserId != team.leaderUserId) {
                            return const Center(
                              child: Padding(
                                padding: EdgeInsets.symmetric(horizontal: 24),
                                child: Text(
                                  '이 팀의 리더만 친구를 초대할 수 있어요.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    color: _Colors.textSub,
                                  ),
                                ),
                              ),
                            );
                          }

                          final remaining = _remainingSlots(team);
                          final excluded = {
                            ...team.acceptedUserIds,
                            ...team.pendingInviteeIds,
                          };

                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Padding(
                                padding: const EdgeInsets.fromLTRB(
                                  20,
                                  12,
                                  20,
                                  4,
                                ),
                                child: Text(
                                  remaining <= 0
                                      ? '지금은 더 초대할 수 있는 자리가 없어요.'
                                      : '최대 $remaining명까지 선택할 수 있어요.',
                                  style: const TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 13,
                                    color: _Colors.textSub,
                                  ),
                                ),
                              ),
                              Expanded(
                                child: FriendsListStreamBody(
                                  currentUserId: _currentUserId!,
                                  friendService: _friendService,
                                  mode: FriendsListStreamMode.picker,
                                  excludedFriendUserIds: excluded,
                                  selectedFriendUserIds: _selected,
                                  formatAddedAt: _formatAddedAt,
                                  pickerMaxAdditionalSelections: remaining,
                                  pickerSelectedCount: _selected.length,
                                  onPickerToggle: (item, willSelect) =>
                                      _onToggle(item, willSelect, remaining),
                                ),
                              ),
                              Padding(
                                padding: EdgeInsets.fromLTRB(
                                  20,
                                  8,
                                  20,
                                  16 + MediaQuery.paddingOf(context).bottom,
                                ),
                                child: CupertinoButton(
                                  padding: EdgeInsets.zero,
                                  onPressed: _sending ||
                                          _selected.isEmpty ||
                                          remaining <= 0
                                      ? null
                                      : _sendInvites,
                                  child: Container(
                                    width: double.infinity,
                                    height: 50,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: _sending ||
                                              _selected.isEmpty ||
                                              remaining <= 0
                                          ? _Colors.line
                                          : _Colors.primary,
                                      borderRadius: BorderRadius.circular(25),
                                    ),
                                    child: _sending
                                        ? const CupertinoActivityIndicator(
                                            color: CupertinoColors.white,
                                          )
                                        : Text(
                                            '초대 보내기'
                                                '${_selected.isEmpty ? '' : ' (${_selected.length})'}',
                                            style: TextStyle(
                                              fontFamily: 'Pretendard',
                                              fontSize: 16,
                                              fontWeight: FontWeight.w700,
                                              color: _selected.isEmpty ||
                                                      remaining <= 0
                                                  ? _Colors.textSub
                                                  : CupertinoColors.white,
                                            ),
                                          ),
                                  ),
                                ),
                              ),
                            ],
                          );
                        },
                      ),
      ),
    );
  }
}
