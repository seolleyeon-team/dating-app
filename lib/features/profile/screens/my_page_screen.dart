// =============================================================================
// 내 페이지 화면
// 경로: lib/features/profile/screens/my_page_screen.dart
// =============================================================================

import 'dart:async';
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../../services/ask_service.dart';
import '../../../services/auth_service.dart';
import '../../chat/services/chat_service.dart';
import '../../../services/kakao_friend_invite_helper.dart';
import '../../../services/friend_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

class _AppColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color backgroundLight = Color(0xFFFFFFFF);
  static const Color surface = Color(0xFFF9F9F9);
  static const Color textMain = Color(0xFF1A1A1A);
  static const Color textSub = Color(0xFF8E8E93);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color purple50 = Color(0xFFFAF5FF);
  static const Color purple500 = Color(0xFF8B5CF6);
  static const Color emerald50 = Color(0xFFECFDF5);
  static const Color emerald500 = Color(0xFF10B981);
}

class MyPageScreen extends StatefulWidget {
  final Function(int)? onNavTap;

  const MyPageScreen({super.key, this.onNavTap});

  @override
  State<MyPageScreen> createState() => _MyPageScreenState();
}

class _MyPageScreenState extends State<MyPageScreen> {
  final _authService = AuthService();
  final _userService = UserService();
  final _friendService = FriendService();
  final _storageService = StorageService();
  final ChatService _chatService = ChatService();
  final AskService _askService = AskService();
  String? _currentUserId;
  bool _isInvitingFriends = false;
  OverlayEntry? _inviteToastEntry;
  Timer? _inviteToastTimer;

  String userName = '사용자 이름';
  String nickname = '닉네임';
  String? avatarUrl;

  int receivedHearts = 0;
  int friendsCount = 0;

  static const String defaultAvatarUrl =
      'https://lh3.googleusercontent.com/aida-public/AB6AXuAlamN6vna7onuxl6KAi_ZQF4inDOBV3szCSXLpbhKJBNMkA0GXEDwrk5twXPOs4LXS0G6ll7xVVnOu1xZIw3T23aOT20DZSwGXtD9KIye2kWfMoFNzq5XlSx8ubmnLS6wjbHBO_4uLkcv1ZGtJsN4_0SNfDo3apAeahRCJaJrzcoXrOl2m4mBTntOfUhvYG_8NcfWaWWb6x_3H0pxtW_aiZouvzrVG0P3gcL7VaYRfb2ifME_bMeHZSrJbaMnA3yGCgQH5eufdWC1f';

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
    loadUser();
  }

  Future<void> _loadCurrentUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (!mounted) return;
    setState(() => _currentUserId = kakaoUserId);
  }

  Future<void> loadUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final user = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || user == null) return;
    final canReadFriends = await _authService.ensureFirebaseSessionForKakao(
      kakaoUserId,
    );
    final actualFriendsCount = canReadFriends
        ? await _friendService.getFriendsCount(kakaoUserId).catchError(
            (_) => (user['friendsCount'] as num?)?.toInt() ?? 0,
          )
        : (user['friendsCount'] as num?)?.toInt() ?? 0;

    final onboardingRaw = user['onboarding'];
    final onboarding = onboardingRaw is Map
        ? Map<String, dynamic>.from(onboardingRaw)
        : <String, dynamic>{};

    final photoUrlsRaw = onboarding['photoUrls'];
    final onboardingPhotoUrls = photoUrlsRaw is List
        ? photoUrlsRaw.whereType<String>().toList()
        : <String>[];

    final mainPhotoUrl = onboardingPhotoUrls.isNotEmpty
        ? onboardingPhotoUrls.first
        : null;

    setState(() {
      nickname = (onboarding['nickname']?.toString().isNotEmpty ?? false)
          ? onboarding['nickname'].toString()
          : '닉네임';
      userName = nickname;

      // 우선순위:
      // 1) onboarding.photoUrls의 첫 번째 사진
      // 2) 기존 profileImageUrl
      // 3) null이면 defaultAvatarUrl 사용
      avatarUrl = (mainPhotoUrl != null && mainPhotoUrl.isNotEmpty)
          ? mainPhotoUrl
          : user['profileImageUrl']?.toString();

      receivedHearts = (user['receivedHearts'] as num?)?.toInt() ?? 0;
      friendsCount = actualFriendsCount;
    });
  }

  Future<void> _inviteFriends() async {
    if (_isInvitingFriends) return;

    HapticFeedback.mediumImpact();
    setState(() => _isInvitingFriends = true);

    try {
      await KakaoFriendInviteHelper.createAndShareKakaoInvite(
        inviterDisplayName: nickname,
      );
      _showInviteSnackBar('카카오톡으로 초대 링크를 보냈어요');
    } catch (e) {
      _showInviteSnackBar(
        e.toString().replaceFirst('Exception: ', ''),
        isError: true,
      );
    } finally {
      if (mounted) {
        setState(() => _isInvitingFriends = false);
      }
    }
  }

  void _showInviteSnackBar(String message, {bool isError = false}) {
    _inviteToastTimer?.cancel();
    _inviteToastEntry?.remove();
    _inviteToastEntry = null;

    final overlay = Overlay.maybeOf(context, rootOverlay: true);
    if (overlay == null) return;

    final bottomOffset = MediaQuery.of(context).padding.bottom + 32;
    final entry = OverlayEntry(
      builder: (_) => Positioned(
        left: 20,
        right: 20,
        bottom: bottomOffset,
        child: IgnorePointer(
          child: _InviteToast(
            message: message,
            isError: isError,
          ),
        ),
      ),
    );

    _inviteToastEntry = entry;
    overlay.insert(entry);

    _inviteToastTimer = Timer(const Duration(seconds: 2), () {
      _inviteToastEntry?.remove();
      _inviteToastEntry = null;
    });
  }

  @override
  void dispose() {
    _inviteToastTimer?.cancel();
    _inviteToastEntry?.remove();
    super.dispose();
  }

  Future<void> _confirmLogout() async {
    final shouldLogout = await showCupertinoDialog<bool>(
      context: context,
      useRootNavigator: true,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(
          '로그아웃',
          style: TextStyle(fontFamily: 'Pretendard'),
        ),
        content: const Text(
          '정말 로그아웃 하시겠습니까?',
          style: TextStyle(fontFamily: 'Pretendard'),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(
              '취소',
              style: TextStyle(fontFamily: 'Pretendard'),
            ),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(
              '확인',
              style: TextStyle(fontFamily: 'Pretendard'),
            ),
          ),
        ],
      ),
    );

    if (shouldLogout != true) return;

    await _storageService.clearAll();

    if (!mounted) return;

    Navigator.of(
      context,
      rootNavigator: true,
    ).pushNamedAndRemoveUntil(RouteNames.terms, (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.surface,
      child: Stack(
        children: [
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: (_currentUserId != null && _currentUserId!.isNotEmpty)
                    ? StreamBuilder<int>(
                        stream: _askService.unreadReceivedCount(
                          _currentUserId!,
                        ),
                        builder: (context, askSnap) {
                          final hasUnread = (askSnap.data ?? 0) > 0;
                          return _Header(
                            showAsksBadge: hasUnread,
                            onAsksInbox: () {
                              Navigator.of(
                                context,
                                rootNavigator: true,
                              ).pushNamed(RouteNames.asksInbox);
                            },
                            onSettings: () async {
                              await Navigator.of(
                                context,
                                rootNavigator: true,
                              ).pushNamed(RouteNames.settings);
                              await loadUser();
                            },
                          );
                        },
                      )
                    : _Header(
                        onAsksInbox: () {
                          Navigator.of(
                            context,
                            rootNavigator: true,
                          ).pushNamed(RouteNames.asksInbox);
                        },
                        onSettings: () async {
                          await Navigator.of(
                            context,
                            rootNavigator: true,
                          ).pushNamed(RouteNames.settings);
                          await loadUser();
                        },
                      ),
              ),
              SliverToBoxAdapter(
                child: _ProfileCard(
                  userName: userName,
                  nickname: nickname,
                  avatarUrl: avatarUrl ?? defaultAvatarUrl,
                  receivedHearts: receivedHearts,
                  friendsCount: friendsCount,
                  onEditAvatar: () async {
                    await Navigator.of(
                      context,
                      rootNavigator: true,
                    ).pushNamed(RouteNames.profileEdit);
                    await loadUser();
                  },
                  onReceivedHeartsTap: () => Navigator.of(
                    context,
                    rootNavigator: true,
                  ).pushNamed(RouteNames.receivedHearts),
                  onFriendsTap: () => Navigator.of(
                    context,
                    rootNavigator: true,
                  ).pushNamed(RouteNames.friendsList),
                ),
              ),
              SliverToBoxAdapter(
                child: _MenuList(
                  onEditProfile: () async {
                    await Navigator.of(
                      context,
                      rootNavigator: true,
                    ).pushNamed(RouteNames.profileEdit);
                    await loadUser();
                  },
                  onRecharge: () => Navigator.of(
                    context,
                    rootNavigator: true,
                  ).pushNamed(RouteNames.heartCharge),
                  onInviteFriends: _inviteFriends,
                  isInviteLoading: _isInvitingFriends,
                ),
              ),
              SliverToBoxAdapter(
                child: _LogoutButton(onLogout: _confirmLogout),
              ),
              SliverToBoxAdapter(child: SizedBox(height: bottomPadding + 100)),
            ],
          ),
          Positioned(
            left: 24,
            right: 24,
            bottom: bottomPadding + 16,
            child: (_currentUserId == null || _currentUserId!.isEmpty)
                ? _FloatingNavBar(
                    onTap: (index) {
                      widget.onNavTap?.call(index);
                    },
                    showChatBadge: false,
                  )
                : StreamBuilder<bool>(
                    stream: _chatService.hasAnyUnreadChats(_currentUserId!),
                    builder: (context, snapshot) {
                      final hasUnread = snapshot.data == true;
                      return _FloatingNavBar(
                        onTap: (index) {
                          widget.onNavTap?.call(index);
                        },
                        showChatBadge: hasUnread,
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _InviteToast extends StatelessWidget {
  final String message;
  final bool isError;

  const _InviteToast({
    required this.message,
    required this.isError,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: isError
            ? CupertinoColors.systemRed.withValues(alpha: 0.92)
            : _AppColors.gray800.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.14),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: CupertinoColors.white,
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final VoidCallback? onSettings;
  final VoidCallback? onAsksInbox;
  final bool showAsksBadge;

  const _Header({
    this.onSettings,
    this.onAsksInbox,
    this.showAsksBadge = false,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
        decoration: BoxDecoration(
          color: _AppColors.backgroundLight.withValues(alpha: 0.8),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              '내 페이지',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 21,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.3,
                color: _AppColors.textMain,
              ),
            ),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    onAsksInbox?.call();
                  },
                  child: SizedBox(
                    width: 40,
                    height: 40,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        const Center(
                          child: Icon(
                            CupertinoIcons.tray_fill,
                            size: 23,
                            color: _AppColors.gray800,
                          ),
                        ),
                        if (showAsksBadge)
                          Positioned(
                            right: 4,
                            top: 4,
                            child: Container(
                              width: 10,
                              height: 10,
                              decoration: BoxDecoration(
                                color: _AppColors.primary,
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: _AppColors.backgroundLight,
                                  width: 1.5,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    onSettings?.call();
                  },
                  child: Container(
                    width: 40,
                    height: 40,
                    decoration: const BoxDecoration(shape: BoxShape.circle),
                    child: const Icon(
                      CupertinoIcons.gear,
                      size: 24,
                      color: _AppColors.gray800,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  final String userName;
  final String nickname;
  final String avatarUrl;
  final int receivedHearts;
  final int friendsCount;
  final VoidCallback? onEditAvatar;
  final VoidCallback? onReceivedHeartsTap;
  final VoidCallback? onFriendsTap;

  const _ProfileCard({
    required this.userName,
    required this.nickname,
    required this.avatarUrl,
    required this.receivedHearts,
    required this.friendsCount,
    this.onEditAvatar,
    this.onReceivedHeartsTap,
    this.onFriendsTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.fromLTRB(0, 32, 0, 40),
      decoration: BoxDecoration(
        color: _AppColors.backgroundLight,
        borderRadius: const BorderRadius.only(
          bottomLeft: Radius.circular(32),
          bottomRight: Radius.circular(32),
        ),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            top: -100,
            left: -50,
            right: -50,
            child: Container(
              height: 200,
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    _AppColors.pink50.withValues(alpha: 0.5),
                    _AppColors.backgroundLight.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          Column(
            children: [
              Stack(
                children: [
                  Container(
                    width: 128,
                    height: 128,
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: const LinearGradient(
                        begin: Alignment.topRight,
                        end: Alignment.bottomLeft,
                        colors: [Color(0xFFFBCFE8), Color(0xFFE9D5FF)],
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: CupertinoColors.black.withValues(alpha: 0.05),
                          blurRadius: 40,
                          offset: const Offset(0, 10),
                        ),
                      ],
                    ),
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: const BoxDecoration(
                        color: CupertinoColors.white,
                        shape: BoxShape.circle,
                      ),
                      child: Container(
                        decoration: const BoxDecoration(
                          shape: BoxShape.circle,
                          color: _AppColors.pink50,
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Image.network(
                          avatarUrl,
                          key: ValueKey(avatarUrl),
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => const Icon(
                            CupertinoIcons.person_fill,
                            size: 48,
                            color: _AppColors.gray400,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    bottom: 4,
                    right: 4,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: onEditAvatar,
                      child: Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: CupertinoColors.white,
                          shape: BoxShape.circle,
                          border: Border.all(color: _AppColors.gray100),
                          boxShadow: [
                            BoxShadow(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.1,
                              ),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: const Icon(
                          CupertinoIcons.pencil,
                          size: 18,
                          color: _AppColors.gray400,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Text(
                userName,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                nickname,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: _AppColors.textSub,
                ),
              ),
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  GestureDetector(
                    onTap: onReceivedHeartsTap,
                    child: _StatItem(label: '받은 하트', value: receivedHearts),
                  ),
                  Container(
                    width: 1,
                    height: 32,
                    margin: const EdgeInsets.symmetric(horizontal: 32),
                    color: _AppColors.gray200,
                  ),
                  GestureDetector(
                    onTap: onFriendsTap,
                    child: _StatItem(label: '친구', value: friendsCount),
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

class _StatItem extends StatelessWidget {
  final String label;
  final int value;

  const _StatItem({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          '$value',
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _AppColors.gray800,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 12,
            color: _AppColors.gray400,
          ),
        ),
      ],
    );
  }
}

class _MenuList extends StatelessWidget {
  final VoidCallback? onEditProfile;
  final VoidCallback? onRecharge;
  final VoidCallback? onInviteFriends;
  final bool isInviteLoading;

  const _MenuList({
    this.onEditProfile,
    this.onRecharge,
    this.onInviteFriends,
    this.isInviteLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.backgroundLight,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.04),
              blurRadius: 12,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          children: [
            _MenuItem(
              icon: CupertinoIcons.person,
              iconBgColor: _AppColors.pink50,
              iconColor: _AppColors.primary,
              label: '프로필 편집',
              onTap: onEditProfile,
            ),
            Container(
              height: 1,
              color: _AppColors.gray100.withValues(alpha: 0.5),
            ),
            _MenuItem(
              icon: CupertinoIcons.creditcard,
              iconBgColor: _AppColors.purple50,
              iconColor: _AppColors.purple500,
              label: '머니 충전',
              onTap: onRecharge,
            ),
            Container(
              height: 1,
              color: _AppColors.gray100.withValues(alpha: 0.5),
            ),
            _MenuItem(
              icon: CupertinoIcons.person_add,
              iconBgColor: _AppColors.emerald50,
              iconColor: _AppColors.emerald500,
              label: '친구 초대',
              onTap: onInviteFriends,
              isLoading: isInviteLoading,
            ),
          ],
        ),
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final Color iconBgColor;
  final Color iconColor;
  final String label;
  final VoidCallback? onTap;
  final bool isLoading;

  const _MenuItem({
    required this.icon,
    required this.iconBgColor,
    required this.iconColor,
    required this.label,
    this.onTap,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: isLoading ? null : () {
        HapticFeedback.selectionClick();
        onTap?.call();
      },
      child: Container(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: iconBgColor,
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 22, color: iconColor),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                  color: _AppColors.gray800,
                ),
              ),
            ),
            isLoading
                ? const CupertinoActivityIndicator()
                : const Icon(
                    CupertinoIcons.chevron_right,
                    size: 20,
                    color: _AppColors.gray300,
                  ),
          ],
        ),
      ),
    );
  }
}

class _LogoutButton extends StatelessWidget {
  final VoidCallback? onLogout;

  const _LogoutButton({this.onLogout});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: onLogout,
          child: const Text(
            '로그아웃',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.gray400,
            ),
          ),
        ),
      ),
    );
  }
}

class _FloatingNavBar extends StatelessWidget {
  final Function(int index)? onTap;
  final bool showChatBadge;

  const _FloatingNavBar({this.onTap, this.showChatBadge = false});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 24),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(color: _AppColors.gray100),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _NavItem(
                icon: CupertinoIcons.heart_fill,
                label: '설레연',
                onTap: () => onTap?.call(0),
              ),
              _NavItem(
                icon: CupertinoIcons.chat_bubble,
                label: '채팅',
                showBadge: showChatBadge,
                onTap: () => onTap?.call(1),
              ),
              _NavItem(
                icon: CupertinoIcons.calendar,
                label: '이벤트',
                onTap: () => onTap?.call(2),
              ),
              _NavItem(
                icon: CupertinoIcons.tree,
                label: '대나무숲',
                onTap: () => onTap?.call(3),
              ),
              _NavItem(
                icon: CupertinoIcons.person,
                label: '내 페이지',
                isActive: true,
                onTap: () => onTap?.call(4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final bool showBadge;
  final VoidCallback? onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    this.isActive = false,
    this.showBadge = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: SizedBox(
        width: 48,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Icon(
                  icon,
                  size: 24,
                  color: isActive ? _AppColors.primary : _AppColors.gray400,
                ),
                if (showBadge)
                  Positioned(
                    right: -2,
                    top: -2,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: Color(0xFF10B981),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 10,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                color: isActive ? _AppColors.primary : _AppColors.gray400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
