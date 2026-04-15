// =============================================================================
// 채팅 목록 화면
// 경로: lib/features/chat/screens/chat_list_screen.dart
// =============================================================================

import 'dart:ui';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/constants/app_colors.dart';
import '../../../router/route_names.dart';
import '../../../services/storage_service.dart';
import '../models/chat_room_data.dart';
import '../services/chat_service.dart';

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
    );
  }
}

// =============================================================================
// 메인 화면
// =============================================================================
class ChatListScreen extends StatefulWidget {
  final VoidCallback? onFilter;
  final Function(String chatId)? onChatTap;
  final Function(int tabIndex)? onTabChange;
  final Function(int navIndex)? onNavTap;

  const ChatListScreen({
    super.key,
    this.onFilter,
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

  String? _currentKakaoUserId;
  bool _isLoading = true;

  static const List<_ChatItem> _baseChats = [
    _ChatItem(
      id: '1',
      name: '김지수',
      avatarUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBtt7Y2vSpmfeZkZz9MgWhu1gNFZz4EW0bZI4gS-x-Mz5CuOT5xQHNgU0Vi4PbzkGuzaBQtk7R-27MK-kukpLLD9mRT899HBUConFqkslrJW_YzCt8mvJrr6kgOhy-Rh5WRRWnstRxeBrsZe9hRihlFxYShp1cHsn6YGlcG810RH6oc04uEgm4lQ3brO0E0N16z0XtvjXOUEAiTBhrLp07VpCGlkhNbzGdnKO0AqpqEXv20rUI-mAomZzZhfDi8j9BBM4GMj1CikI25',
      lastMessage: '오늘 저녁에 시간 어때요? 강남역 근처에 맛있는 파스타집 알아요!',
      time: '방금 전',
      isOnline: true,
      hasUnread: true,
      sortOrder: 500,
    ),
    _ChatItem(
      id: '2',
      name: '박민준',
      avatarUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDT0RK8vCMZ1fdHvltVWDurwmelCqxdies0jRqVZ_i25_eXkBCWJSMVbt1RHAXD45KRadkUNxR_I2QrUqowUVd6LAmnoRziNg9prWLp5-enwv4B2WnmBUopjrYkYLJ8Cfg4V19xvQCLCy3YiL3OWgiSdunOve4HFVg5cw_LyBCbsjMVnDX5loPDI6HE6DZspiFsBGHimsJGffCUK-K7s0tzpMe7fprq9qO_3oB0jD_PqSGgr3Iu-txc3QGpFn_AS4QNEI9m3BKCzum',
      lastMessage: '반가워요! 프로필 사진 분위기가 정말 좋으시네요 ㅎㅎ',
      time: '10분 전',
      hasUnread: true,
      hasGradientBorder: true,
      sortOrder: 400,
    ),
    _ChatItem(
      id: '3',
      name: '이서연',
      avatarUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCaoLaT2eg0Mr_CWMHTb5DFnC5NtnwIvbYSr7QlFAo429bhcRjjwZ9eM3KXCGGry_-VwTlGW47t69Ak613q9yN48tItC8XhxXVqQ86xWtAwYvjMYdr_P9OK5iF8KAOItKthh-1k1Yyb8Hw9Xsg0sNvpr2Lk-jPDZV8ycVaam8IOELv_NnjuKvJTEjGQ4_0BXIEfDkJW9k_eUdW51hXHAqnnL2vhABTODCwEnScNf9OS2fWATu403bThgZNQPrpzISgd7fJTNXMop1Xu',
      lastMessage: '네 알겠습니다~ 그럼 주말에 뵙는 걸로 할게요!',
      time: '1시간 전',
      sortOrder: 300,
    ),
    _ChatItem(
      id: '4',
      name: '최현우',
      avatarUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBkclIYukugmfdmt_FqHn8n6ngOFy_HcntISLBJEEeng4mqga5wP8CTpo5nSbBLPrfKTmN1Cn5J65q8775JhJgm1JgGcKCUWg4SOouC6CFrYgDZxNGA2zgHwl5QWNh_gHj6N1Sq7I5YEeXtZ4oW4I12Sd21200BxMAniftmmGyNlkrjFtnR8ejLC3BdX7HJ8d2kvjG6mMxINka5PxHf-MuEX4QWFqSihtVj8ap_6F8IRbkAMAFu0GIa_J-0voPIWJoa2yTA138wQo28',
      lastMessage: '사진 보내드렸습니다. 확인해주세요.',
      time: '어제',
      isGrayscale: true,
      sortOrder: 200,
    ),
    _ChatItem(
      id: '5',
      name: '정하나',
      avatarUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuD5daUKQ65R86r5mD6ge1Dbq2r2x9s6mfF64QKG-Ok03q5Bk0RKkYndnQPpn2_qabOdm5-c4EXRI0RcmvAMRcdizRxM_MdpXu6n29zGbZckSgCt-BkONB0jM-ABrBhZOSyiQCZF1u9d7ukDbTa1eRA1CW7xgYecLFR_MFTngH-H503o6iKizja6XfMSkR7958WwJEMQ9lQ1lZAyr0rIZAP4-gQOOnEFV1H0w8SADoT7BJvmFJa6q5CKX4NFUuEur0R27-wnqmopSJM1',
      lastMessage: '즐거운 하루 보내세요 :)',
      time: '어제',
      sortOrder: 100,
    ),
  ];

  static const _ChatItem _fakeChat = _ChatItem(
    id: 'fake_user_1',
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
  );

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();

    debugPrint('CHAT LIST current user: $kakaoUserId');

    if (!mounted) return;

    setState(() {
      _currentKakaoUserId = kakaoUserId;
      _isLoading = false;
    });
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

    final fallbackName = partnerId == 'fake_user_1' ? '가짜 계정 1' : '알 수 없음';

    return _ChatItem(
      id: partnerId,
      chatRoomId: doc.id,
      name: (partnerInfo['nickname']?.toString().isNotEmpty ?? false)
          ? partnerInfo['nickname'].toString()
          : fallbackName,
      avatarUrl: partnerInfo['avatarUrl']?.toString() ?? '',
      lastMessage: (data['lastMessage']?.toString().isNotEmpty ?? false)
          ? data['lastMessage'].toString()
          : '채팅을 시작해 보세요!',
      time: _formatLastMessageTime(data['lastMessageAt']),
      isOnline: partnerId == 'fake_user_1',
      hasUnread: false,
      hasGradientBorder: false,
      isGrayscale: false,
      sortOrder: 999999,
      isFakeAccountRoom: partnerId == 'fake_user_1',
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
    );
  }

  List<_ChatItem> get _sortedChats {
    final chats = [..._baseChats];

    if (_currentKakaoUserId != null && _currentKakaoUserId != 'fake_user_1') {
      chats.add(_fakeChat);
    }

    chats.sort((a, b) => b.sortOrder.compareTo(a.sortOrder));
    return chats;
  }

  @override
  Widget build(BuildContext context) {
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
    final scaffoldBg = isDark ? AppColorsDark.background : CupertinoColors.white;

    return CupertinoPageScaffold(
      backgroundColor: scaffoldBg,
      child: Stack(
        children: [
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(child: _Header(onFilter: widget.onFilter)),
              SliverToBoxAdapter(
                child: _TabBar(onTabChange: widget.onTabChange),
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
                      debugPrint('CHAT LIST ERROR: ${snapshot.error}');

                      if (currentUserId != 'fake_user_1') {
                        final fallbackChats = <_ChatItem>[
                          _buildFakeRoomItem(currentUserId),
                        ];

                        return SliverPadding(
                          padding: EdgeInsets.fromLTRB(
                            24,
                            8,
                            24,
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
                                onTap: () {
                                  if (widget.onChatTap != null) {
                                    widget.onChatTap!(
                                      chat.chatRoomId ?? chat.id,
                                    );
                                  } else {
                                    Navigator.of(
                                      context,
                                      rootNavigator: true,
                                    ).pushNamed(
                                      RouteNames.chatRoom,
                                      arguments: ChatRoomData(
                                        chatRoomId: chat.chatRoomId ?? '',
                                        partnerId: chat.id,
                                        partnerName: chat.name,
                                        partnerAvatarUrl: chat.avatarUrl,
                                        lastMessage: chat.lastMessage,
                                        lastMessageTime: chat.time,
                                      ),
                                    );
                                  }
                                },
                              );
                            }, childCount: fallbackChats.length),
                          ),
                        );
                      }

                      final seol = Theme.of(context).extension<SeolThemeColors>()!;
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 80),
                          child: Center(
                            child: Text(
                              '채팅 목록을 불러오지 못했어요',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 15,
                                color: seol.gray400,
                              ),
                            ),
                          ),
                        ),
                      );
                    }

                    if (!snapshot.hasData) {
                      if (currentUserId != 'fake_user_1') {
                        final fallbackChats = <_ChatItem>[
                          _buildFakeRoomItem(currentUserId),
                        ];

                        return SliverPadding(
                          padding: EdgeInsets.fromLTRB(
                            24,
                            8,
                            24,
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
                                onTap: () {
                                  if (widget.onChatTap != null) {
                                    widget.onChatTap!(
                                      chat.chatRoomId ?? chat.id,
                                    );
                                  } else {
                                    Navigator.of(
                                      context,
                                      rootNavigator: true,
                                    ).pushNamed(
                                      RouteNames.chatRoom,
                                      arguments: ChatRoomData(
                                        chatRoomId: chat.chatRoomId ?? '',
                                        partnerId: chat.id,
                                        partnerName: chat.name,
                                        partnerAvatarUrl: chat.avatarUrl,
                                        lastMessage: chat.lastMessage,
                                        lastMessageTime: chat.time,
                                      ),
                                    );
                                  }
                                },
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

                    final docs = [...snapshot.data!.docs];

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
                        _mapRoomDocToChatItem(doc, currentUserId),
                      );
                    }

                    _ChatItem? fakeChatRoom;
                    final normalChats = <_ChatItem>[];

                    for (final chat in mappedChats) {
                      if (chat.id == 'fake_user_1') {
                        fakeChatRoom = chat;
                      } else {
                        normalChats.add(chat);
                      }
                    }

                    if (currentUserId != 'fake_user_1') {
                      fakeChatRoom ??= _buildFakeRoomItem(currentUserId);
                    }

                    final firestoreChats = <_ChatItem>[
                      if (fakeChatRoom != null) fakeChatRoom,
                      ...normalChats,
                    ];

                    if (firestoreChats.isEmpty) {
                      final seol = Theme.of(context).extension<SeolThemeColors>()!;
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 80),
                          child: Center(
                            child: Text(
                              currentUserId == 'fake_user_1'
                                  ? '아직 받은 채팅이 없어요'
                                  : '채팅을 시작해 보세요!',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
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
                        24,
                        8,
                        24,
                        bottomPadding + 120,
                      ),
                      sliver: SliverList(
                        delegate: SliverChildBuilderDelegate((context, index) {
                          final chat = firestoreChats[index];

                          if (chat.chatRoomId == null ||
                              chat.chatRoomId!.isEmpty) {
                            return _ChatListItem(
                              chat: chat,
                              onTap: () {
                                if (widget.onChatTap != null) {
                                  widget.onChatTap!(chat.chatRoomId ?? chat.id);
                                } else {
                                  Navigator.of(
                                    context,
                                    rootNavigator: true,
                                  ).pushNamed(
                                    RouteNames.chatRoom,
                                    arguments: ChatRoomData(
                                      chatRoomId: chat.chatRoomId ?? '',
                                      partnerId: chat.id,
                                      partnerName: chat.name,
                                      partnerAvatarUrl: chat.avatarUrl,
                                      lastMessage: chat.lastMessage,
                                      lastMessageTime: chat.time,
                                    ),
                                  );
                                }
                              },
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
                                onTap: () {
                                  if (widget.onChatTap != null) {
                                    widget.onChatTap!(
                                      chatWithUnread.chatRoomId ??
                                          chatWithUnread.id,
                                    );
                                  } else {
                                    Navigator.of(
                                      context,
                                      rootNavigator: true,
                                    ).pushNamed(
                                      RouteNames.chatRoom,
                                      arguments: ChatRoomData(
                                        chatRoomId:
                                            chatWithUnread.chatRoomId ?? '',
                                        partnerId: chatWithUnread.id,
                                        partnerName: chatWithUnread.name,
                                        partnerAvatarUrl:
                                            chatWithUnread.avatarUrl,
                                        lastMessage: chatWithUnread.lastMessage,
                                        lastMessageTime: chatWithUnread.time,
                                      ),
                                    );
                                  }
                                },
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
                    colors: [
                      scaffoldBg.withValues(alpha: 0),
                      scaffoldBg,
                    ],
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            left: 24,
            right: 24,
            bottom: bottomPadding + 32,
            child: currentUserId.isEmpty
                ? _BottomNavBar(onTap: widget.onNavTap)
                : StreamBuilder<bool>(
                    stream: _chatService.hasAnyUnreadChats(currentUserId),
                    builder: (context, snapshot) {
                      final hasUnread = snapshot.data ?? false;
                      return _BottomNavBar(
                        onTap: widget.onNavTap,
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

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onFilter;

  const _Header({this.onFilter});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final titleColor = seol.gray800;
    final filterBg = isDark
        ? CupertinoColors.white.withValues(alpha: 0.08)
        : CupertinoColors.black.withValues(alpha: 0.03);

    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '채팅',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 28,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.5,
                color: titleColor,
              ),
            ),
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                HapticFeedback.lightImpact();
                onFilter?.call();
              },
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: filterBg,
                ),
                child: Icon(
                  CupertinoIcons.slider_horizontal_3,
                  size: 24,
                  color: titleColor,
                ),
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
class _TabBar extends StatefulWidget {
  final Function(int tabIndex)? onTabChange;

  const _TabBar({this.onTabChange});

  @override
  State<_TabBar> createState() => _TabBarState();
}

class _TabBarState extends State<_TabBar> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: Row(
        children: [
          _TabChip(
            label: '1:1',
            isSelected: _selectedIndex == 0,
            onTap: () {
              setState(() => _selectedIndex = 0);
              widget.onTabChange?.call(0);
            },
          ),
          const SizedBox(width: 12),
          _TabChip(
            label: '3:3',
            isSelected: _selectedIndex == 1,
            onTap: () {
              setState(() => _selectedIndex = 1);
              widget.onTabChange?.call(1);
            },
          ),
          const SizedBox(width: 12),
          _TabChip(
            label: 'AI 어시스턴트',
            icon: CupertinoIcons.sparkles,
            isSelected: _selectedIndex == 2,
            onTap: () {
              setState(() => _selectedIndex = 2);
              widget.onTabChange?.call(2);
            },
          ),
        ],
      ),
    );
  }
}

class _TabChip extends StatelessWidget {
  final String label;
  final IconData? icon;
  final bool isSelected;
  final VoidCallback? onTap;

  const _TabChip({
    required this.label,
    this.icon,
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
            if (icon != null) ...[
              Icon(
                icon,
                size: 14,
                color: isSelected ? CupertinoColors.white : seol.gray400,
              ),
              const SizedBox(width: 6),
            ],
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
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
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: seol.cardSurface,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            _Avatar(
              imageUrl: chat.avatarUrl,
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
                          fontFamily: 'Pretendard',
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
                            fontFamily: 'Pretendard',
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: seol.gray400,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          chat.lastMessage,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 13,
                            fontWeight: chat.hasUnread
                                ? FontWeight.w500
                                : FontWeight.w400,
                            color: chat.hasUnread
                                ? seol.gray800
                                : seol.gray400,
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
// 아바타
// =============================================================================
class _Avatar extends StatelessWidget {
  final String imageUrl;
  final bool isOnline;
  final bool hasGradientBorder;
  final bool isGrayscale;

  const _Avatar({
    required this.imageUrl,
    this.isOnline = false,
    this.hasGradientBorder = false,
    this.isGrayscale = false,
  });

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final safeImageUrl = imageUrl;
    final ringColor = seol.cardSurface;

    Widget avatar = Container(
      width: 60,
      height: 60,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: seol.gray100),
        color: seol.gray100,
      ),
      clipBehavior: Clip.antiAlias,
      child: safeImageUrl.isEmpty
          ? Icon(
              CupertinoIcons.person_fill,
              color: seol.gray400,
              size: 28,
            )
          : isGrayscale
          ? ColorFiltered(
              colorFilter: const ColorFilter.mode(
                CupertinoColors.systemGrey,
                BlendMode.saturation,
              ),
              child: Image.network(
                safeImageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Icon(
                  CupertinoIcons.person_fill,
                  color: seol.gray400,
                  size: 28,
                ),
              ),
            )
          : Image.network(
              safeImageUrl,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Icon(
                CupertinoIcons.person_fill,
                color: seol.gray400,
                size: 28,
              ),
            ),
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
          child: Image.network(
            safeImageUrl,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Icon(
              CupertinoIcons.person_fill,
              color: seol.gray400,
            ),
          ),
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

// =============================================================================
// 하단 네비게이션
// =============================================================================
class _BottomNavBar extends StatelessWidget {
  final Function(int index)? onTap;
  final bool showChatBadge;

  const _BottomNavBar({this.onTap, this.showChatBadge = false});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final navBg = isDark
        ? const Color(0xFF221A28).withValues(alpha: 0.92)
        : CupertinoColors.white.withValues(alpha: 0.95);
    final navBorder = isDark
        ? AppColorsDark.border.withValues(alpha: 0.55)
        : CupertinoColors.white.withValues(alpha: 0.4);

    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: navBg,
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: navBorder,
            ),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.15),
                blurRadius: 40,
                offset: const Offset(0, 10),
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
                icon: CupertinoIcons.chat_bubble_fill,
                label: '채팅',
                isActive: true,
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
    final primary = Theme.of(context).colorScheme.primary;
    final inactiveColor = Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF7A6B76)
        : _AppColors.gray400;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              Icon(
                icon,
                size: 24,
                color: isActive ? primary : inactiveColor,
              ),
              if (showBadge)
                Positioned(
                  right: -2,
                  top: -2,
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      color: _AppColors.onlineGreen,
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
              fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
              letterSpacing: -0.2,
              color: isActive ? primary : inactiveColor,
            ),
          ),
        ],
      ),
    );
  }
}
