import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/auth_service.dart';
import '../../../services/event_team_service.dart';
import '../../../services/friend_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../profile/widgets/friends_list_shared.dart';

/// 이벤트 등에서 친구를 여러 명 선택해 요청을 보낼 때 쓰는 화면 (친구 목록 변형)
class AddFriendScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onMessage;
  final Function(int)? onTabChanged;

  const AddFriendScreen({
    super.key,
    this.onBack,
    this.onMessage,
    this.onTabChanged,
  });

  @override
  State<AddFriendScreen> createState() => _AddFriendScreenState();
}

class _AddFriendScreenState extends State<AddFriendScreen> {
  final AuthService _authService = AuthService();
  final StorageService _storageService = StorageService();
  final FriendService _friendService = FriendService();
  final UserService _userService = UserService();
  final EventTeamService _eventTeamService = EventTeamService();

  String? _currentUserId;
  bool _isAuthReady = false;
  bool _canReadFriends = false;
  int _friendCountHint = 0;
  bool _isSending = false;

  /// 선택된 친구 userId 목록
  final Set<String> _selectedFriendIds = {};

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final userId = await _storageService.getKakaoUserId();
    if (!mounted) return;

    var canReadFriends = false;
    var friendCountHint = 0;

    if (userId != null && userId.isNotEmpty) {
      final userProfile = await _userService.getUserProfile(userId);
      friendCountHint = (userProfile?['friendsCount'] as num?)?.toInt() ?? 0;
      canReadFriends = await _authService.ensureFirebaseSessionForVerifiedUser(
        userId,
      );
    }

    if (!mounted) return;
    setState(() {
      _currentUserId = userId;
      _isAuthReady = true;
      _canReadFriends = canReadFriends;
      _friendCountHint = friendCountHint;
    });
  }

  void _onPickerToggle(FriendListItem item, bool willSelect) {
    HapticFeedback.selectionClick();
    setState(() {
      if (willSelect) {
        _selectedFriendIds.add(item.friendUserId);
      } else {
        _selectedFriendIds.remove(item.friendUserId);
      }
    });
  }

  /// 요청 보내기 버튼 핸들러
  Future<void> _onSendRequest() async {
    HapticFeedback.mediumImpact();
    if (_selectedFriendIds.isEmpty || _isSending) return;

    final uid = _currentUserId;
    if (uid == null || uid.isEmpty) return;

    // 팀 ID 가져오기
    final teamSetupId = await _storageService.getEventTeamSetupDraftId(uid);
    if (teamSetupId == null || teamSetupId.isEmpty) {
      _briefAlert('팀 정보를 찾을 수 없어요. 팀 구성 화면에서 다시 시도해주세요.');
      return;
    }

    setState(() => _isSending = true);

    var sent = 0;
    final targets = List<String>.from(_selectedFriendIds);
    try {
      for (final inviteeUserId in targets) {
        await _eventTeamService.createInvite(
          teamSetupId: teamSetupId,
          inviteeUserId: inviteeUserId,
        );
        sent++;
      }
      if (mounted && sent > 0) {
        HapticFeedback.mediumImpact();
        Navigator.of(context).maybePop();
      }
    } catch (e) {
      if (mounted) {
        final msg = e.toString()
            .replaceFirst('Exception: ', '')
            .replaceFirst('StateError: ', '');
        _briefAlert(msg);
      }
    } finally {
      if (mounted) setState(() => _isSending = false);
    }
  }

  void _briefAlert(String message) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
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

  String _formatAddedAt(DateTime? dateTime) {
    if (dateTime == null) return '추가일 정보 없음';
    final month = dateTime.month.toString().padLeft(2, '0');
    final day = dateTime.day.toString().padLeft(2, '0');
    return '${dateTime.year}.$month.$day 친구가 되었어요';
  }

  bool get _looksLikeNoFriendsYet => _friendCountHint <= 0;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: FriendsListSharedColors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: FriendsListSharedColors.surface.withValues(
          alpha: 0.92,
        ),
        border: const Border(
          bottom: BorderSide(color: FriendsListSharedColors.line, width: 0.5),
        ),
        middle: const Text(
          '친구 목록',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: FriendsListSharedColors.textMain,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            if (widget.onBack != null) {
              widget.onBack!();
              return;
            }
            Navigator.of(context).maybePop();
          },
          child: const Icon(
            CupertinoIcons.back,
            color: FriendsListSharedColors.textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: _currentUserId == null
            ? const Center(child: CupertinoActivityIndicator())
            : !_isAuthReady
                ? const Center(child: CupertinoActivityIndicator())
                : !_canReadFriends
                    ? (_looksLikeNoFriendsYet
                        ? const FriendsListEmptyMessage(
                            icon: CupertinoIcons.person_2,
                            title: '아직 추가된 친구가 없어요',
                            subtitle:
                                '친구 초대 링크를 보내 설레연 친구를 만들어보세요',
                          )
                        : const FriendsListEmptyMessage(
                            icon: CupertinoIcons.lock_circle,
                            title: '친구 목록을 열 수 없어요',
                            subtitle:
                                '학교 이메일 인증이 완료된 계정으로 다시 로그인해주세요',
                          ))
                    : Column(
                        children: [
                          Expanded(
                            child: FriendsListStreamBody(
                              currentUserId: _currentUserId!,
                              friendService: _friendService,
                              mode: FriendsListStreamMode.picker,
                              formatAddedAt: _formatAddedAt,
                              selectedFriendUserIds: _selectedFriendIds,
                              onPickerToggle: _onPickerToggle,
                              emptyOnPermissionDeniedWhenNoFriendsHint: true,
                              friendCountHint: _friendCountHint,
                            ),
                          ),
                          _buildBottomSendButton(),
                        ],
                      ),
      ),
    );
  }

  Widget _buildBottomSendButton() {
    final bool isActive = _selectedFriendIds.isNotEmpty && !_isSending;
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      decoration: const BoxDecoration(
        color: CupertinoColors.white,
        border: Border(
          top: BorderSide(
            color: FriendsListSharedColors.line,
            width: 0.5,
          ),
        ),
      ),
      child: GestureDetector(
        onTap: isActive ? _onSendRequest : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: double.infinity,
          height: 52,
          decoration: BoxDecoration(
            color: isActive
                ? const Color(0xFFEF3976)
                : const Color(0xFFEF3976).withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(14),
          ),
          alignment: Alignment.center,
          child: _isSending
              ? const CupertinoActivityIndicator(color: CupertinoColors.white)
              : Text(
                  _selectedFriendIds.isEmpty
                      ? '요청 보내기'
                      : '요청 보내기 (${_selectedFriendIds.length})',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                    color: CupertinoColors.white.withValues(
                      alpha: isActive ? 1.0 : 0.7,
                    ),
                  ),
                ),
        ),
      ),
    );
  }
}
