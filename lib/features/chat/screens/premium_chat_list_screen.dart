// =============================================================================
// 채팅 목록 화면
// 경로: lib/features/chat/screens/chat_list_screen.dart
// =============================================================================

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/constants/app_colors.dart';
import '../../../router/route_names.dart';
import '../../../services/firebase_diagnostics.dart';
import '../../../services/push_notification_service.dart';
import '../../../services/storage_service.dart';
import '../../../shared/widgets/chat_profile_photo_avatar.dart';
import '../../../shared/widgets/capture_protected_image.dart';
import '../../../shared/widgets/seolleyeon_bottom_navigation_bar.dart';
import '../../../shared/utils/dev_entry_policy.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../models/chat_room_data.dart';
import '../services/chat_service.dart';
import '../services/support_chat_service.dart';
import '../utils/chat_room_tab.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color onlineGreen = Color(0xFF22C55E);
}

// =============================================================================
// 채팅 모델
// =============================================================================
class _ChatItem {
  final String id;
  final String name;
  final String avatarUrl;
  final String lastMessage;
  final String time;
  final String? chatRoomId;
  final bool isOnline;
  final bool hasUnread;
  final bool hasGradientBorder;
  final bool isGrayscale;
  final int sortOrder;
  final bool isFakeAccountRoom;
  final bool isWithdrawn;

  /// 3:3 단체방 (블라인드 취향 미팅 / 시즌 미팅). 상대 한 명이 아니라
  /// 방 이름과 참가자 요약을 보여주고, 사진 대신 단체 아이콘을 쓴다.
  final bool isGroupRoom;
  final String? memberSummary;

  const _ChatItem({
    required this.id,
    required this.name,
    required this.avatarUrl,
    required this.lastMessage,
    required this.time,
    this.chatRoomId,
    this.isOnline = false,
    this.hasUnread = false,
    this.hasGradientBorder = false,
    this.isGrayscale = false,
    this.sortOrder = 0,
    this.isFakeAccountRoom = false,
    this.isWithdrawn = false,
    this.isGroupRoom = false,
    this.memberSummary,
  });

  _ChatItem copyWith({
    String? id,
    String? name,
    String? avatarUrl,
    String? lastMessage,
    String? time,
    String? chatRoomId,
    bool? isOnline,
    bool? hasUnread,
    bool? hasGradientBorder,
    bool? isGrayscale,
    int? sortOrder,
    bool? isFakeAccountRoom,
    bool? isWithdrawn,
    bool? isGroupRoom,
    String? memberSummary,
  }) {
    return _ChatItem(
      id: id ?? this.id,
      name: name ?? this.name,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      lastMessage: lastMessage ?? this.lastMessage,
      time: time ?? this.time,
      chatRoomId: chatRoomId ?? this.chatRoomId,
      isOnline: isOnline ?? this.isOnline,
      hasUnread: hasUnread ?? this.hasUnread,
      hasGradientBorder: hasGradientBorder ?? this.hasGradientBorder,
      isGrayscale: isGrayscale ?? this.isGrayscale,
      sortOrder: sortOrder ?? this.sortOrder,
      isFakeAccountRoom: isFakeAccountRoom ?? this.isFakeAccountRoom,
      isWithdrawn: isWithdrawn ?? this.isWithdrawn,
      isGroupRoom: isGroupRoom ?? this.isGroupRoom,
      memberSummary: memberSummary ?? this.memberSummary,
    );
  }

  /// 방 열기 인자. 3:3 방은 상대 한 명이 없으므로 방 이름만 넘긴다.
  ChatRoomData toRoomData() => ChatRoomData(
    chatRoomId: chatRoomId ?? '',
    partnerId: isGroupRoom ? '' : id,
    partnerName: name,
    partnerAvatarUrl: isGroupRoom ? null : avatarUrl,
    partnerUniversity: isGroupRoom ? '3:3 단체 채팅' : '',
    lastMessage: lastMessage,
    lastMessageTime: time,
  );
}

// =============================================================================
// 메인 화면
// =============================================================================
class ChatListScreen extends StatefulWidget {
  final Function(String chatId)? onChatTap;
  final Function(int tabIndex)? onTabChange;
  final Function(int navIndex)? onNavTap;

  const ChatListScreen({
    super.key,
    this.onChatTap,
    this.onTabChange,
    this.onNavTap,
  });

  @override
  State<ChatListScreen> createState() => _ChatListScreenState();
}

class _ChatListScreenState extends State<ChatListScreen> {
  final StorageService _storageService = StorageService();
  final ChatService _chatService = ChatService();
  final SupportChatService _supportChatService = SupportChatService();

  String? _currentKakaoUserId;
  bool _isLoading = true;

  /// 현재 탭. 목업이 아니라 실제 room discriminator(chat_room_tab.dart)로
  /// 같은 참가자 쿼리 결과를 1:1 / 3:3 으로 나눠 보여준다.
  ChatRoomTab _tab = ChatRoomTab.direct;

  void _selectTab(ChatRoomTab tab) {
    if (_tab == tab) return;
    setState(() => _tab = tab);
    widget.onTabChange?.call(tab.index);
  }

  @override
  void initState() {
    super.initState();
    PushNotificationService.instance.setChatListVisible(true);
    _loadCurrentUser();
  }

  @override
  void deactivate() {
    PushNotificationService.instance.setChatListVisible(false);
    super.deactivate();
  }

  @override
  void activate() {
    super.activate();
    PushNotificationService.instance.setChatListVisible(true);
  }

  @override
  void dispose() {
    PushNotificationService.instance.setChatListVisible(false);
    super.dispose();
  }

  Future<void> _loadCurrentUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    final resolvedUserId =
        kakaoUserId ?? FirebaseAuth.instance.currentUser?.uid;

    debugPrint(
      'CHAT LIST current user: ${PrivacyLogUtils.idFingerprint(resolvedUserId)}',
    );

    if (!mounted) return;

    setState(() {
      _currentKakaoUserId = resolvedUserId;
      _isLoading = false;
    });
  }

  String _firebaseProjectId() {
    try {
      final projectId = Firebase.app().options.projectId;
      return projectId.isEmpty ? '없음' : projectId;
    } catch (_) {
      return 'Firebase 초기화 안 됨';
    }
  }

  String _chatListErrorReason(
    String code,
    String currentUserId,
    String? firebaseUid,
  ) {
    switch (code) {
      case 'permission-denied':
        if (firebaseUid == null) {
          return 'Firebase Auth 세션이 없습니다. 로그인은 끝났지만 현재 앱에 Firebase 사용자가 없습니다.';
        }
        if (firebaseUid != currentUserId) {
          return 'Firebase UID와 앱에 저장된 사용자 ID가 다릅니다. 잘못된 계정으로 채팅을 조회하고 있습니다.';
        }
        return '로그인 세션은 일치하지만 Firestore 보안 규칙이 이 사용자의 채팅방 조회를 거부했습니다.';
      case 'unauthenticated':
        return 'Firebase Auth 세션이 없거나 만료되었습니다. 테스트 계정으로 다시 로그인해 주세요.';
      case 'failed-precondition':
        return 'Firestore 인덱스 또는 쿼리 사전 조건 오류입니다. 아래 상세 메시지에 인덱스 안내가 있는지 확인해 주세요.';
      case 'unavailable':
        return 'Firebase 서버에 연결할 수 없습니다. 네트워크 또는 Firebase 장애를 확인해 주세요.';
      case 'deadline-exceeded':
        return 'Firebase 요청 시간이 초과되었습니다. 네트워크 상태를 확인해 주세요.';
      case 'not-found':
        return '요청한 Firestore 리소스를 찾지 못했습니다.';
      default:
        return 'Firebase가 채팅방 조회를 거부했거나 알 수 없는 오류가 발생했습니다.';
    }
  }

  String _chatListErrorDetails(Object error, String currentUserId) {
    final exception = error is FirebaseException ? error : null;
    final code = exception?.code.trim().isNotEmpty == true
        ? exception!.code
        : 'unknown';
    final firebaseUid = FirebaseAuth.instance.currentUser?.uid;
    final safeMessage = FirebaseDiagnostics.safeErrorForLog(
      error,
    ).replaceAll(RegExp(r'\s+'), ' ').trim();
    final shortenedMessage = safeMessage.length <= 280
        ? safeMessage
        : '${safeMessage.substring(0, 280)}…';

    return [
      '원인: ${_chatListErrorReason(code, currentUserId, firebaseUid)}',
      '오류 코드: ${exception?.plugin ?? 'unknown'}/$code',
      '앱 사용자 ID: ${PrivacyLogUtils.idFingerprint(currentUserId)}',
      'Firebase Auth UID: ${PrivacyLogUtils.idFingerprint(firebaseUid)}',
      'UID 일치: ${firebaseUid == null
          ? '확인 불가(세션 없음)'
          : firebaseUid == currentUserId
          ? '예'
          : '아니오'}',
      'Firebase 프로젝트: ${_firebaseProjectId()}',
      if (shortenedMessage.isNotEmpty) '상세 메시지: $shortenedMessage',
    ].join('\n');
  }

  String _formatLastMessageTime(dynamic ts) {
    if (ts is! Timestamp) return '';
    final dt = ts.toDate();
    final now = DateTime.now();

    final isToday =
        dt.year == now.year && dt.month == now.month && dt.day == now.day;

    if (isToday) {
      final hour = dt.hour > 12 ? dt.hour - 12 : (dt.hour == 0 ? 12 : dt.hour);
      final minute = dt.minute.toString().padLeft(2, '0');
      final period = dt.hour >= 12 ? '오후' : '오전';
      return '$period $hour:$minute';
    }

    return '${dt.month}/${dt.day}';
  }

  /// 3:3 단체방 항목. 블라인드 미팅은 얼굴·실명을 공개하지 않으므로 사진 없이
  /// 방 이름 + 참가자 요약만 보여준다.
  _ChatItem _mapGroupRoomDocToChatItem(
    QueryDocumentSnapshot<Map<String, dynamic>> doc,
    String currentUserId,
  ) {
    final data = doc.data();
    return _ChatItem(
      id: doc.id,
      chatRoomId: doc.id,
      name: groupRoomDisplayName(data),
      avatarUrl: '',
      lastMessage: (data['lastMessage']?.toString().isNotEmpty ?? false)
          ? data['lastMessage'].toString()
          : '3:3 채팅방이 열렸어요. 인사를 나눠보세요!',
      time: _formatLastMessageTime(data['lastMessageAt']),
      sortOrder: 999999,
      isGroupRoom: true,
      memberSummary: groupRoomMemberSummary(data, currentUserId),
    );
  }

  _ChatItem _mapRoomDocToChatItem(
    QueryDocumentSnapshot<Map<String, dynamic>> doc,
    String currentUserId,
  ) {
    final data = doc.data();

    final participantIds = List<String>.from(data['participantIds'] ?? []);
    final otherParticipants = participantIds
        .where((id) => id != currentUserId)
        .toList();

    final partnerId = otherParticipants.isNotEmpty
        ? otherParticipants.first
        : '';

    final participantInfo = Map<String, dynamic>.from(
      data['participantInfo'] ?? {},
    );

    final partnerInfo = partnerId.isNotEmpty
        ? Map<String, dynamic>.from(participantInfo[partnerId] ?? {})
        : <String, dynamic>{};
    final isWithdrawn =
        partnerInfo['isWithdrawn'] == true ||
        (data['withdrawnParticipantIds'] is List &&
            (data['withdrawnParticipantIds'] as List)
                .map((e) => '$e')
                .contains(partnerId));

    final fallbackName = partnerId == 'fake_user_1' ? '가짜 계정 1' : '알 수 없음';

    return _ChatItem(
      id: partnerId,
      chatRoomId: doc.id,
      name: isWithdrawn
          ? '탈퇴한 사용자'
          : (partnerInfo['nickname']?.toString().isNotEmpty ?? false)
          ? partnerInfo['nickname'].toString()
          : fallbackName,
      avatarUrl: isWithdrawn ? '' : partnerInfo['avatarUrl']?.toString() ?? '',
      lastMessage: (data['lastMessage']?.toString().isNotEmpty ?? false)
          ? data['lastMessage'].toString()
          : '채팅을 시작해 보세요!',
      time: _formatLastMessageTime(data['lastMessageAt']),
      isOnline: partnerId == 'fake_user_1',
      hasUnread: false,
      hasGradientBorder: false,
      isGrayscale: isWithdrawn,
      sortOrder: 999999,
      isFakeAccountRoom: partnerId == 'fake_user_1',
      isWithdrawn: isWithdrawn,
    );
  }

  _ChatItem _buildFakeRoomItem(String currentUserId) {
    final roomId = _chatService.buildDirectRoomId(currentUserId, 'fake_user_1');

    return _ChatItem(
      id: 'fake_user_1',
      chatRoomId: roomId,
      name: '가짜 계정 1',
      avatarUrl: '',
      lastMessage: '채팅을 시작해 보세요!',
      time: '',
      isOnline: true,
      hasUnread: false,
      hasGradientBorder: false,
      isGrayscale: false,
      sortOrder: 999999,
      isFakeAccountRoom: true,
      isWithdrawn: false,
    );
  }

  /// 방 열기. 1:1 은 상대 정보와 함께, 3:3 은 정확한 단체방 id 로 진입한다.
  void _openChat(_ChatItem chat) {
    if (widget.onChatTap != null) {
      widget.onChatTap!(chat.chatRoomId ?? chat.id);
      return;
    }
    Navigator.of(
      context,
      rootNavigator: true,
    ).pushNamed(RouteNames.chatRoom, arguments: chat.toRoomData());
  }

  @override
  Widget build(BuildContext context) {
    PushNotificationService.instance.setChatListVisible(true);
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final currentUserId = _currentKakaoUserId ?? '';

    if (_isLoading) {
      return CupertinoPageScaffold(
        backgroundColor: Theme.of(context).brightness == Brightness.dark
            ? AppColorsDark.background
            : CupertinoColors.white,
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final scaffoldBg = isDark
        ? AppColorsDark.background
        : CupertinoColors.white;

    return CupertinoPageScaffold(
      backgroundColor: scaffoldBg,
      child: Stack(
        children: [
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              const SliverToBoxAdapter(child: _Header()),
              SliverToBoxAdapter(
                child: _TabBar(selected: _tab, onChanged: _selectTab),
              ),
              FutureBuilder<bool>(
                future: _supportChatService.isOperations(),
                builder: (context, snapshot) {
                  if (snapshot.data != true) {
                    return const SliverToBoxAdapter(child: SizedBox.shrink());
                  }
                  return SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                      child: CupertinoButton.filled(
                        onPressed: () => Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.supportUserDirectory),
                        child: const Text('사용자 목록'),
                      ),
                    ),
                  );
                },
              ),
              if (currentUserId.isEmpty)
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.only(top: 80),
                    child: Center(child: CupertinoActivityIndicator()),
                  ),
                )
              else
                StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
                  stream: _chatService.chatRoomsStream(currentUserId),
                  builder: (context, snapshot) {
                    if (snapshot.hasError) {
                      debugPrint(
                        'CHAT LIST ERROR: ${PrivacyLogUtils.errorSummary(snapshot.error!)}',
                      );

                      if (DevEntryPolicy.allowTestAccountEntry &&
                          currentUserId != 'fake_user_1' &&
                          _tab == ChatRoomTab.direct) {
                        final fallbackChats = <_ChatItem>[
                          _buildFakeRoomItem(currentUserId),
                        ];

                        return SliverPadding(
                          padding: EdgeInsets.fromLTRB(
                            16,
                            8,
                            16,
                            bottomPadding + 120,
                          ),
                          sliver: SliverList(
                            delegate: SliverChildBuilderDelegate((
                              context,
                              index,
                            ) {
                              final chat = fallbackChats[index];

                              return _ChatListItem(
                                chat: chat,
                                onTap: () => _openChat(chat),
                              );
                            }, childCount: fallbackChats.length),
                          ),
                        );
                      }

                      final seol = Theme.of(
                        context,
                      ).extension<SeolThemeColors>()!;
                      final errorDetails = kDebugMode
                          ? _chatListErrorDetails(
                              snapshot.error!,
                              currentUserId,
                            )
                          : null;
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(16, 80, 16, 24),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  '채팅 목록을 불러오지 못했어요',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontFamily: 'NanumSquareRound',
                                    fontSize: 15,
                                    color: seol.gray400,
                                  ),
                                ),
                                if (errorDetails != null) ...[
                                  const SizedBox(height: 14),
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: seol.gray100,
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: SelectableText(
                                      errorDetails,
                                      style: TextStyle(
                                        fontFamily: 'NanumSquareRound',
                                        fontSize: 11,
                                        height: 1.45,
                                        color: seol.bodyText,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                      );
                    }

                    if (!snapshot.hasData) {
                      if (DevEntryPolicy.allowTestAccountEntry &&
                          currentUserId != 'fake_user_1' &&
                          _tab == ChatRoomTab.direct) {
                        final fallbackChats = <_ChatItem>[
                          _buildFakeRoomItem(currentUserId),
                        ];

                        return SliverPadding(
                          padding: EdgeInsets.fromLTRB(
                            16,
                            8,
                            16,
                            bottomPadding + 120,
                          ),
                          sliver: SliverList(
                            delegate: SliverChildBuilderDelegate((
                              context,
                              index,
                            ) {
                              final chat = fallbackChats[index];

                              return _ChatListItem(
                                chat: chat,
                                onTap: () => _openChat(chat),
                              );
                            }, childCount: fallbackChats.length),
                          ),
                        );
                      }

                      return const SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.only(top: 80),
                          child: Center(child: CupertinoActivityIndicator()),
                        ),
                      );
                    }

                    // 같은 참가자 쿼리 결과를 탭(1:1 / 3:3)으로 나눈다. 멤버십은
                    // 쿼리(arrayContains uid)와 rules 가 서버 기준으로 보장한다.
                    final docs = filterRoomsForTab(
                      snapshot.data!.docs,
                      _tab,
                      (doc) => doc.data(),
                    );

                    docs.sort((a, b) {
                      final aTs = a.data()['lastMessageAt'] as Timestamp?;
                      final bTs = b.data()['lastMessageAt'] as Timestamp?;

                      final aMs = aTs?.millisecondsSinceEpoch ?? 0;
                      final bMs = bTs?.millisecondsSinceEpoch ?? 0;

                      return bMs.compareTo(aMs);
                    });

                    final mappedChats = <_ChatItem>[];
                    for (final doc in docs) {
                      mappedChats.add(
                        _tab == ChatRoomTab.group
                            ? _mapGroupRoomDocToChatItem(doc, currentUserId)
                            : _mapRoomDocToChatItem(doc, currentUserId),
                      );
                    }

                    _ChatItem? fakeChatRoom;
                    final normalChats = <_ChatItem>[];

                    for (final chat in mappedChats) {
                      if (!chat.isGroupRoom && chat.id == 'fake_user_1') {
                        fakeChatRoom = chat;
                      } else {
                        normalChats.add(chat);
                      }
                    }

                    if (DevEntryPolicy.allowTestAccountEntry &&
                        currentUserId != 'fake_user_1' &&
                        _tab == ChatRoomTab.direct) {
                      fakeChatRoom ??= _buildFakeRoomItem(currentUserId);
                    }

                    final firestoreChats = <_ChatItem>[
                      if (fakeChatRoom != null) fakeChatRoom,
                      ...normalChats,
                    ];

                    if (firestoreChats.isEmpty) {
                      final seol = Theme.of(
                        context,
                      ).extension<SeolThemeColors>()!;
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 80),
                          child: Center(
                            child: Text(
                              _tab.emptyMessage,
                              key: ValueKey('chat-empty-${_tab.name}'),
                              style: TextStyle(
                                fontFamily: 'NanumSquareRound',
                                fontSize: 15,
                                color: seol.gray400,
                              ),
                            ),
                          ),
                        ),
                      );
                    }

                    return SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        16,
                        8,
                        16,
                        bottomPadding + 120,
                      ),
                      sliver: SliverList(
                        delegate: SliverChildBuilderDelegate((context, index) {
                          final chat = firestoreChats[index];

                          if (chat.chatRoomId == null ||
                              chat.chatRoomId!.isEmpty) {
                            return _ChatListItem(
                              chat: chat,
                              onTap: () => _openChat(chat),
                            );
                          }

                          return StreamBuilder<int>(
                            stream: _chatService.unreadCountStream(
                              roomId: chat.chatRoomId!,
                              userId: currentUserId,
                            ),
                            builder: (context, unreadSnapshot) {
                              final unreadCount = unreadSnapshot.data ?? 0;
                              final chatWithUnread = chat.copyWith(
                                hasUnread: unreadCount > 0,
                              );

                              return _ChatListItem(
                                chat: chatWithUnread,
                                onTap: () => _openChat(chatWithUnread),
                              );
                            },
                          );
                        }, childCount: firestoreChats.length),
                      ),
                    );
                  },
                ),
            ],
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 96,
            child: IgnorePointer(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [scaffoldBg.withValues(alpha: 0), scaffoldBg],
                  ),
                ),
              ),
            ),
          ),
          if (currentUserId.isEmpty)
            SeolleyeonBottomNavPositioned(
              currentTab: BottomNavTab.chat,
              onTap: widget.onNavTap,
            )
          else
            StreamBuilder<bool>(
              stream: _chatService.hasAnyUnreadChats(currentUserId),
              builder: (context, snapshot) {
                final hasUnread = snapshot.data ?? false;
                return SeolleyeonBottomNavPositioned(
                  currentTab: BottomNavTab.chat,
                  onTap: widget.onNavTap,
                  showChatBadge: hasUnread,
                );
              },
            ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final titleColor = seol.gray800;

    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
        child: Row(
          children: [
            Text(
              '채팅',
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 28,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.5,
                color: titleColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 탭 바
// =============================================================================
/// 1:1 / 3:3 탭. 상태는 화면이 소유하고(실제 목록 필터), 여기서는 표시만 한다.
class _TabBar extends StatelessWidget {
  final ChatRoomTab selected;
  final ValueChanged<ChatRoomTab> onChanged;

  const _TabBar({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: Row(
        children: [
          for (final tab in ChatRoomTab.values) ...[
            if (tab != ChatRoomTab.values.first) const SizedBox(width: 12),
            _TabChip(
              key: ValueKey('chat-tab-${tab.name}'),
              label: tab.label,
              isSelected: selected == tab,
              onTap: () => onChanged(tab),
            ),
          ],
        ],
      ),
    );
  }
}

class _TabChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback? onTap;

  const _TabChip({
    super.key,
    required this.label,
    this.isSelected = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.selectionClick();
        onTap?.call();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? primary : seol.gray100,
          borderRadius: BorderRadius.circular(20),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: primary.withValues(alpha: 0.15),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                color: isSelected ? CupertinoColors.white : seol.gray400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 채팅 리스트 아이템
// =============================================================================
class _ChatListItem extends StatelessWidget {
  final _ChatItem chat;
  final VoidCallback? onTap;

  const _ChatListItem({required this.chat, this.onTap});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        decoration: BoxDecoration(
          color: seol.cardSurface,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            if (chat.isGroupRoom)
              _GroupAvatar(key: ValueKey('chat-group-avatar-${chat.id}'))
            else
              _Avatar(
                imageUrl: chat.avatarUrl,
                chatRoomId: chat.chatRoomId,
                targetUid: chat.id,
                useChatRealPhoto: !chat.isFakeAccountRoom,
                isOnline: chat.isOnline,
                hasGradientBorder: chat.hasGradientBorder,
                isGrayscale: chat.isGrayscale,
              ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        chat.name,
                        style: TextStyle(
                          fontFamily: 'NanumSquareRound',
                          fontSize: 15,
                          fontWeight: chat.hasUnread
                              ? FontWeight.w700
                              : FontWeight.w600,
                          letterSpacing: -0.2,
                          color: seol.gray800,
                        ),
                      ),
                      if (chat.time.isNotEmpty)
                        Text(
                          chat.time,
                          style: TextStyle(
                            fontFamily: 'NanumSquareRound',
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: seol.gray400,
                          ),
                        ),
                    ],
                  ),
                  if (chat.memberSummary != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      chat.memberSummary!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: 'NanumSquareRound',
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: seol.gray400,
                      ),
                    ),
                  ],
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          chat.lastMessage,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontFamily: 'NanumSquareRound',
                            fontSize: 13,
                            fontWeight: chat.hasUnread
                                ? FontWeight.w500
                                : FontWeight.w400,
                            color: chat.hasUnread ? seol.gray800 : seol.gray400,
                            height: 1.3,
                          ),
                        ),
                      ),
                      if (chat.hasUnread) ...[
                        const SizedBox(width: 8),
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: _AppColors.onlineGreen,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.onlineGreen.withValues(
                                  alpha: 0.3,
                                ),
                                blurRadius: 4,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
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
// 3:3 단체방 아바타 (사진 없음 — 블라인드 미팅은 얼굴을 공개하지 않는다)
// =============================================================================
class _GroupAvatar extends StatelessWidget {
  const _GroupAvatar({super.key});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;
    return Container(
      width: 60,
      height: 60,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: seol.gray100),
        color: primary.withValues(alpha: 0.10),
      ),
      alignment: Alignment.center,
      child: Icon(CupertinoIcons.person_3_fill, color: primary, size: 26),
    );
  }
}

// =============================================================================
// 아바타
// =============================================================================
class _Avatar extends StatelessWidget {
  final String imageUrl;
  final String? chatRoomId;
  final String targetUid;
  final bool useChatRealPhoto;
  final bool isOnline;
  final bool hasGradientBorder;
  final bool isGrayscale;

  const _Avatar({
    required this.imageUrl,
    required this.targetUid,
    this.chatRoomId,
    this.useChatRealPhoto = false,
    this.isOnline = false,
    this.hasGradientBorder = false,
    this.isGrayscale = false,
  });

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final safeImageUrl = imageUrl;
    final ringColor = seol.cardSurface;
    final canUseChatRealPhoto =
        useChatRealPhoto &&
        (chatRoomId?.isNotEmpty ?? false) &&
        targetUid.isNotEmpty;

    Widget avatarImage({double size = 60}) {
      if (canUseChatRealPhoto) {
        return ChatProfilePhotoAvatar(
          chatRoomId: chatRoomId!,
          targetUid: targetUid,
          fallbackImageUrl: safeImageUrl,
          size: size,
          grayscale: isGrayscale,
          backgroundColor: seol.gray100,
          placeholderIconColor: _AppColors.gray400,
          placeholderIconSize: 28,
        );
      }
      if (safeImageUrl.isEmpty) {
        return Icon(CupertinoIcons.person_fill, color: seol.gray400, size: 28);
      }
      return CaptureProtectedImage(
        imageUrl: safeImageUrl,
        shape: CaptureProtectedImageShape.circle,
        fit: BoxFit.cover,
        grayscale: isGrayscale,
        backgroundColor: seol.gray100,
        placeholderIconColor: _AppColors.gray400,
        placeholderIconSize: 28,
      );
    }

    Widget avatar = Container(
      width: 60,
      height: 60,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: seol.gray100),
        color: seol.gray100,
      ),
      clipBehavior: Clip.antiAlias,
      child: avatarImage(),
    );

    if (hasGradientBorder) {
      avatar = Container(
        padding: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: const LinearGradient(
            begin: Alignment.topRight,
            end: Alignment.bottomLeft,
            colors: [Color(0xFFFACC15), Color(0xFFFF5A7E), Color(0xFFA855F7)],
          ),
        ),
        child: Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: ringColor, width: 2),
          ),
          clipBehavior: Clip.antiAlias,
          child: avatarImage(size: 56),
        ),
      );
    }

    return Stack(
      children: [
        avatar,
        if (isOnline)
          Positioned(
            bottom: 2,
            right: 2,
            child: Container(
              width: 14,
              height: 14,
              decoration: BoxDecoration(
                color: _AppColors.onlineGreen,
                shape: BoxShape.circle,
                border: Border.all(color: ringColor, width: 2),
              ),
            ),
          ),
      ],
    );
  }
}
