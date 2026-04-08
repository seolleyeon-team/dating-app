import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/friend_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../matching/models/profile_card_args.dart';
import '../widgets/friends_list_shared.dart';

class FriendsListScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onMessage;
  final Function(int)? onTabChanged;

  const FriendsListScreen({
    super.key,
    this.onBack,
    this.onMessage,
    this.onTabChanged,
  });

  @override
  State<FriendsListScreen> createState() => _FriendsListScreenState();
}

class _FriendsListScreenState extends State<FriendsListScreen> {
  final AuthService _authService = AuthService();
  final StorageService _storageService = StorageService();
  final FriendService _friendService = FriendService();
  final UserService _userService = UserService();

  String? _currentUserId;
  bool _isAuthReady = false;
  bool _canReadFriends = false;
  int _friendCountHint = 0;

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
      canReadFriends = await _authService.ensureFirebaseSessionForKakao(userId);
    }

    if (!mounted) return;
    setState(() {
      _currentUserId = userId;
      _isAuthReady = true;
      _canReadFriends = canReadFriends;
      _friendCountHint = friendCountHint;
    });
  }

  void _openFriendProfile(FriendListItem item) {
    HapticFeedback.selectionClick();
    Navigator.of(context, rootNavigator: true).pushNamed(
      RouteNames.profileSpecificDetail,
      arguments: ProfileCardArgs.fromChat(userId: item.friendUserId),
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
                    : FriendsListStreamBody(
                        currentUserId: _currentUserId!,
                        friendService: _friendService,
                        mode: FriendsListStreamMode.browse,
                        formatAddedAt: _formatAddedAt,
                        onBrowseTap: _openFriendProfile,
                        emptyOnPermissionDeniedWhenNoFriendsHint: true,
                        friendCountHint: _friendCountHint,
                      ),
      ),
    );
  }
}
