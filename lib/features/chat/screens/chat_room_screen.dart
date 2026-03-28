import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter/services.dart';

import '../services/chat_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../services/push_notification_service.dart';
import '../../../router/route_names.dart';
import '../../matching/models/profile_card_args.dart';

class _AppColors {
  static const Color primary = Color(0xFF3B5443);
  static const Color backgroundLight = Color(0xFFFAFAF9);
  static const Color bubbleUser = Color(0xFFF5F2EE);
  static const Color bubblePartner = Color(0xFFF0F3F5);
  static const Color textMain = Color(0xFF201F1D);
  static const Color textSubtle = Color(0xFF868E96);
  static const Color stone100 = Color(0xFFF5F5F4);
  static const Color stone200 = Color(0xFFE7E5E4);
  static const Color stone400 = Color(0xFFA8A29E);
  static const Color sendButton = Color(0xFFFFB2C1);
}

enum MessageType { received, sent, promiseRequest, promiseConfirmed }

class _ChatMessage {
  final MessageType type;
  final String text;
  final String time;
  final bool isRead;
  final DateTime sortDateTime;

  final String? promiseId;
  final DateTime? promiseDateTime;
  final String? promisePlace;
  final String? promiseCategory;
  final bool isMineRequest;
  final String? promiseStatus;

  final bool isEdited;
  final DateTime? editedAt;

  const _ChatMessage({
    required this.type,
    required this.text,
    required this.time,
    required this.sortDateTime,
    this.isRead = false,
    this.promiseId,
    this.promiseDateTime,
    this.promisePlace,
    this.promiseCategory,
    this.isMineRequest = false,
    this.promiseStatus,
    this.isEdited = false,
    this.editedAt,
  });

  bool get isExpired {
    if (promiseDateTime == null) return false;
    return promiseDateTime!.isBefore(DateTime.now());
  }

  bool get isPromise =>
      type == MessageType.promiseRequest ||
      type == MessageType.promiseConfirmed;

  _ChatMessage copyWith({
    MessageType? type,
    String? text,
    String? time,
    bool? isRead,
    DateTime? sortDateTime,
    String? promiseId,
    DateTime? promiseDateTime,
    String? promisePlace,
    String? promiseCategory,
    bool? isMineRequest,
    String? promiseStatus,
    bool? isEdited,
    DateTime? editedAt,
  }) {
    return _ChatMessage(
      type: type ?? this.type,
      text: text ?? this.text,
      time: time ?? this.time,
      isRead: isRead ?? this.isRead,
      sortDateTime: sortDateTime ?? this.sortDateTime,
      promiseId: promiseId ?? this.promiseId,
      promiseDateTime: promiseDateTime ?? this.promiseDateTime,
      promisePlace: promisePlace ?? this.promisePlace,
      promiseCategory: promiseCategory ?? this.promiseCategory,
      isMineRequest: isMineRequest ?? this.isMineRequest,
      promiseStatus: promiseStatus ?? this.promiseStatus,
      isEdited: isEdited ?? this.isEdited,
      editedAt: editedAt ?? this.editedAt,
    );
  }
}

class ChatRoomScreen extends StatefulWidget {
  final String chatRoomId;
  final String partnerId;
  final String partnerName;
  final String partnerUniversity;
  final String? partnerAvatarUrl;
  final VoidCallback? onBack;
  final VoidCallback? onMore;
  final Function(String message)? onSend;

  const ChatRoomScreen({
    super.key,
    this.chatRoomId = '',
    this.partnerId = '',
    this.partnerName = 'Kim Min-jun',
    this.partnerUniversity = "Seoul Nat'l Univ",
    this.partnerAvatarUrl,
    this.onBack,
    this.onMore,
    this.onSend,
  });

  @override
  State<ChatRoomScreen> createState() => _ChatRoomScreenState();
}

class _ChatRoomScreenState extends State<ChatRoomScreen> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  static const String _defaultAvatarUrl =
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBbzHXe44kKkm38LFzZYDrJgB6VdcFI1wOqXLhzmXLluq6QpZFzdN4Kwf2jgvTVY0ulkwDXqpPKoaA8SnoMT5qhSFFGurIjc409LZqO6cs9LiNr2XWRHXHTIQhT0_trL5o9o3NSs5xIr8H1FtojhKTzR0P0wp5-9pIeGcdDl9D6vK5Fxv6IA8lfddlamHK7vlvzUfH7SNwgZ7OBgfMReB4O7jfppVehNPNaM5xl6dsuqMZKa2J3QbWJdkCeYQ20949IQZKdQuyh5Iqz';
  static const double _topAreaHeight = 166;

  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  final ChatService _chatService = ChatService();

  String? _currentUserId;
  String _currentUserName = '나';
  String? _currentUserAvatarUrl;
  String _roomId = '';
  String? _initError;
  bool _isReady = false;
  bool _isSending = false;

  void _openPartnerProfileCard() {
    if (widget.partnerId.isEmpty) return;

    Navigator.of(context, rootNavigator: true).pushNamed(
      RouteNames.profileSpecificDetail,
      arguments: ProfileCardArgs.fromChat(userId: widget.partnerId),
    );
  }

  @override
  void initState() {
    super.initState();
    _initChat();
  }

  @override
  void dispose() {
    if (_roomId.isNotEmpty) {
      PushNotificationService.instance.clearOpenedChatRoom(_roomId);
    }
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void deactivate() {
    if (_roomId.isNotEmpty) {
      PushNotificationService.instance.clearOpenedChatRoom(_roomId);
    }
    super.deactivate();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  void _markCurrentRoomAsRead() {
    if (_currentUserId == null || _roomId.isEmpty) return;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _chatService.markMessagesAsRead(
        roomId: _roomId,
        userId: _currentUserId!,
      );
    });
  }

  Future<void> _initChat() async {
    try {
      final kakaoUserId = await _storageService.getKakaoUserId();

      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인 정보가 없습니다.');
      }
      if (widget.partnerId.isEmpty) {
        throw Exception('partnerId 없음');
      }

      final user = await _userService.getUserProfile(kakaoUserId);
      final onboarding = user?['onboarding'];

      _currentUserId = kakaoUserId;
      _currentUserName = (onboarding is Map && onboarding['nickname'] != null)
          ? onboarding['nickname'].toString()
          : (user?['nickname']?.toString() ?? '나');

      String? resolvedAvatarUrl;
      if (onboarding is Map) {
        final photoUrlsRaw = onboarding['photoUrls'];
        if (photoUrlsRaw is List && photoUrlsRaw.isNotEmpty) {
          final firstPhoto = photoUrlsRaw.first?.toString() ?? '';
          if (firstPhoto.isNotEmpty) {
            resolvedAvatarUrl = firstPhoto;
          }
        }
      }
      resolvedAvatarUrl ??= user?['profileImageUrl']?.toString();
      _currentUserAvatarUrl = resolvedAvatarUrl;

      _roomId = widget.chatRoomId.isNotEmpty
          ? widget.chatRoomId
          : _chatService.buildDirectRoomId(kakaoUserId, widget.partnerId);

      await _chatService.ensureDirectRoom(
        roomId: _roomId,
        currentUserId: kakaoUserId,
        partnerId: widget.partnerId,
        currentUserName: _currentUserName,
        partnerName: widget.partnerName,
        currentUserAvatarUrl: _currentUserAvatarUrl,
        partnerAvatarUrl: widget.partnerAvatarUrl,
      );

      PushNotificationService.instance.setOpenedChatRoom(_roomId);

      if (!mounted) return;
      setState(() {
        _isReady = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _initError = e.toString();
        _isReady = false;
      });
    }
  }

  Future<void> _handleSend() async {
    final text = _messageController.text.trim();
    if (text.isEmpty ||
        _currentUserId == null ||
        _roomId.isEmpty ||
        _isSending) {
      return;
    }

    setState(() {
      _isSending = true;
    });

    try {
      _messageController.clear();

      await _chatService.sendTextMessage(
        roomId: _roomId,
        senderId: _currentUserId!,
        text: text,
      );

      widget.onSend?.call(text);
      _scrollToBottom();
    } finally {
      if (!mounted) return;
      setState(() {
        _isSending = false;
      });
    }
  }

  Future<void> _openPromiseSheet({
    String? editingPromiseId,
    DateTime? initialDateTime,
    String? initialCategory,
    String? initialPlace,
  }) async {
    if (_currentUserId == null || _roomId.isEmpty) return;

    final result = await showCupertinoModalPopup<_PromiseFormResult>(
      context: context,
      builder: (context) => _PromiseCreateBottomSheet(
        initialDateTime: initialDateTime,
        initialCategory: initialCategory,
        initialPlace: initialPlace,
      ),
    );

    if (result == null) return;

    if (editingPromiseId != null) {
      await _chatService.updatePromise(
        roomId: _roomId,
        promiseId: editingPromiseId,
        editedBy: _currentUserId!,
        dateTime: result.dateTime,
        place: result.place,
        placeCategory: result.placeCategory,
      );
      return;
    }

    await _chatService.createPromise(
      roomId: _roomId,
      requestedBy: _currentUserId!,
      requestedTo: widget.partnerId,
      dateTime: result.dateTime,
      place: result.place,
      placeCategory: result.placeCategory,
    );
  }

  Future<void> _approvePromise(_ChatMessage message) async {
    if (message.promiseId == null) return;
    await _chatService.acceptPromise(
      roomId: _roomId,
      promiseId: message.promiseId!,
    );
  }

  Future<void> _rejectPromise(_ChatMessage message) async {
    if (message.promiseId == null) return;
    await _chatService.rejectPromise(
      roomId: _roomId,
      promiseId: message.promiseId!,
    );
  }

  Future<void> _deletePromise(_ChatMessage message) async {
    if (message.promiseId == null) return;

    final shouldDelete = await showCupertinoDialog<bool>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('약속 삭제'),
        content: const Text('이 약속을 삭제하시겠어요?'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );

    if (shouldDelete != true) return;

    await _chatService.cancelPromise(
      roomId: _roomId,
      promiseId: message.promiseId!,
    );
  }

  _ChatMessage _mapMessage(Map<String, dynamic> data) {
    final senderId = data['senderId']?.toString() ?? '';
    final text = (data['text'] ?? data['content'] ?? '').toString();
    final type = data['type']?.toString() ?? 'text';
    final ts = data['createdAt'];
    final updatedTs = data['updatedAt'];

    DateTime createdAt = DateTime.fromMillisecondsSinceEpoch(0);
    String timeText = '';

    if (ts is Timestamp) {
      createdAt = ts.toDate();
      final hour = createdAt.hour > 12
          ? createdAt.hour - 12
          : (createdAt.hour == 0 ? 12 : createdAt.hour);
      final minute = createdAt.minute.toString().padLeft(2, '0');
      final period = createdAt.hour >= 12 ? 'PM' : 'AM';
      timeText = '$hour:$minute $period';
    }

    DateTime? promiseDateTime;
    final promiseTs = data['dateTime'];
    if (promiseTs is Timestamp) {
      promiseDateTime = promiseTs.toDate();
    }

    DateTime? editedAt;
    if (updatedTs is Timestamp) {
      editedAt = updatedTs.toDate();
    }

    final isEdited = data['isEdited'] == true;
    final promiseStatus = data['status']?.toString();

    if (type == 'promise_request') {
      return _ChatMessage(
        type: MessageType.promiseRequest,
        text: text.isNotEmpty ? text : '약속 요청',
        time: '',
        sortDateTime: createdAt,
        promiseId: data['promiseId']?.toString(),
        promiseDateTime: promiseDateTime,
        promisePlace: data['place']?.toString(),
        promiseCategory: data['placeCategory']?.toString(),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: promiseStatus ?? 'requested',
        isEdited: isEdited,
        editedAt: editedAt,
      );
    }

    if (type == 'promise_confirmed') {
      return _ChatMessage(
        type: MessageType.promiseConfirmed,
        text: text.isNotEmpty ? text : '약속이 확정되었어요',
        time: '',
        sortDateTime: createdAt,
        promiseId: data['promiseId']?.toString(),
        promiseDateTime: promiseDateTime,
        promisePlace: data['place']?.toString(),
        promiseCategory: data['placeCategory']?.toString(),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: promiseStatus ?? 'confirmed',
        isEdited: isEdited,
        editedAt: editedAt,
      );
    }

    if (type == 'promise_deleted') {
      return _ChatMessage(
        type: MessageType.promiseRequest,
        text: text.isNotEmpty ? text : '약속이 삭제되었어요',
        time: '',
        sortDateTime: createdAt,
        promiseId: data['promiseId']?.toString(),
        promiseDateTime: promiseDateTime,
        promisePlace: data['place']?.toString(),
        promiseCategory: data['placeCategory']?.toString(),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: 'cancelled',
        isEdited: false,
        editedAt: editedAt,
      );
    }

    return _ChatMessage(
      type: senderId == _currentUserId
          ? MessageType.sent
          : MessageType.received,
      text: text,
      time: timeText,
      sortDateTime: createdAt,
      isRead: senderId == _currentUserId,
    );
  }

  List<_ChatMessage> _mergeMessages(List<_ChatMessage> source) {
    final normalMessages = <_ChatMessage>[];
    final promiseMap = <String, _ChatMessage>{};

    for (final message in source) {
      if (!message.isPromise || message.promiseId == null) {
        if (message.promiseStatus != 'rejected' && !message.isExpired) {
          normalMessages.add(message);
        }
        continue;
      }

      if (message.promiseStatus == 'rejected' || message.isExpired) {
        continue;
      }

      if (message.promiseStatus == 'cancelled') {
        if (message.promiseId != null) {
          promiseMap.remove(message.promiseId);
        }
        normalMessages.add(message);
        continue;
      }

      final key = message.promiseId!;

      if (!promiseMap.containsKey(key)) {
        promiseMap[key] = message;
        continue;
      }

      final existing = promiseMap[key]!;

      final merged = existing.copyWith(
        type: message.type == MessageType.promiseConfirmed
            ? MessageType.promiseConfirmed
            : existing.type,
        text: message.type == MessageType.promiseConfirmed
            ? message.text
            : existing.text,
        promiseDateTime: message.promiseDateTime ?? existing.promiseDateTime,
        promisePlace: message.promisePlace ?? existing.promisePlace,
        promiseCategory: message.promiseCategory ?? existing.promiseCategory,
        promiseStatus: message.promiseStatus ?? existing.promiseStatus,
        isMineRequest: existing.isMineRequest,
        sortDateTime: existing.sortDateTime.isBefore(message.sortDateTime)
            ? existing.sortDateTime
            : message.sortDateTime,
        isEdited: existing.isEdited || message.isEdited,
        editedAt: _latestDate(existing.editedAt, message.editedAt),
      );

      promiseMap[key] = merged;
    }

    final mergedList = <_ChatMessage>[...normalMessages, ...promiseMap.values]
      ..sort((a, b) => a.sortDateTime.compareTo(b.sortDateTime));

    return mergedList;
  }

  DateTime? _latestDate(DateTime? a, DateTime? b) {
    if (a == null) return b;
    if (b == null) return a;
    return a.isAfter(b) ? a : b;
  }

  void _ensureOpenedChatRoomRegistered() {
    if (_roomId.isEmpty) return;
    PushNotificationService.instance.setOpenedChatRoom(_roomId);
  }

  @override
  Widget build(BuildContext context) {
    _ensureOpenedChatRoomRegistered();
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          CustomScrollView(
            controller: _scrollController,
            physics: const BouncingScrollPhysics(),
            slivers: [
              const SliverToBoxAdapter(child: SizedBox(height: _topAreaHeight)),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(24, 12, 24, bottomPadding + 120),
                sliver: !_isReady
                    ? SliverToBoxAdapter(
                        child: Center(
                          child: Padding(
                            padding: const EdgeInsets.only(top: 40),
                            child: _initError == null
                                ? const CupertinoActivityIndicator()
                                : Text(
                                    '채팅방을 불러오지 못했어요\n$_initError',
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 14,
                                      color: _AppColors.textSubtle,
                                    ),
                                  ),
                          ),
                        ),
                      )
                    : StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
                        stream: _chatService.messagesStream(_roomId),
                        builder: (context, messageSnapshot) {
                          if (messageSnapshot.connectionState ==
                                  ConnectionState.waiting &&
                              !messageSnapshot.hasData) {
                            return const SliverToBoxAdapter(
                              child: Center(
                                child: Padding(
                                  padding: EdgeInsets.only(top: 40),
                                  child: CupertinoActivityIndicator(),
                                ),
                              ),
                            );
                          }

                          final messageDocs =
                              messageSnapshot.data?.docs ?? const [];

                          _markCurrentRoomAsRead();

                          final mappedMessages = messageDocs
                              .map((doc) => _mapMessage(doc.data()))
                              .toList();
                          final allMessages = _mergeMessages(mappedMessages);

                          if (allMessages.isEmpty) {
                            return const SliverToBoxAdapter(
                              child: Padding(
                                padding: EdgeInsets.only(top: 80),
                                child: Center(
                                  child: Text(
                                    '채팅을 시작해 보세요!',
                                    style: TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 15,
                                      color: _AppColors.textSubtle,
                                    ),
                                  ),
                                ),
                              ),
                            );
                          }

                          _scrollToBottom();

                          return SliverList(
                            delegate: SliverChildBuilderDelegate((
                              context,
                              index,
                            ) {
                              final message = allMessages[index];

                              return _MessageItem(
                                message: message,
                                avatarUrl:
                                    widget.partnerAvatarUrl ??
                                    _defaultAvatarUrl,
                                onApprovePromise: () =>
                                    _approvePromise(message),
                                onRejectPromise: () => _rejectPromise(message),
                                onEditPromise: () => _openPromiseSheet(
                                  editingPromiseId: message.promiseId,
                                  initialDateTime: message.promiseDateTime,
                                  initialCategory: message.promiseCategory,
                                  initialPlace: message.promisePlace,
                                ),
                                onDeletePromise: () => _deletePromise(message),
                                onOpenProfile: _openPartnerProfileCard,
                              );
                            }, childCount: allMessages.length),
                          );
                        },
                      ),
              ),
            ],
          ),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            child: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
              stream: _roomId.isEmpty ? null : _chatService.roomStream(_roomId),
              builder: (context, snapshot) {
                final roomData = snapshot.data?.data();
                final activePromiseRaw = roomData?['activePromise'];
                final activePromise = activePromiseRaw is Map
                    ? Map<String, dynamic>.from(activePromiseRaw)
                    : null;

                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _Header(
                      name: widget.partnerName,
                      university: widget.partnerUniversity,
                      onBack: widget.onBack,
                      onMore: widget.onMore,
                      onPromiseTap: _openPromiseSheet,
                      onProfileTap: _openPartnerProfileCard,
                    ),
                    if (activePromise != null)
                      _ActivePromiseBanner(activePromise: activePromise),
                  ],
                );
              },
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _InputBar(
              controller: _messageController,
              bottomPadding: bottomPadding,
              onSend: _handleSend,
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final String name;
  final String university;
  final VoidCallback? onBack;
  final VoidCallback? onMore;
  final VoidCallback? onPromiseTap;
  final VoidCallback? onProfileTap;

  const _Header({
    required this.name,
    required this.university,
    this.onBack,
    this.onMore,
    this.onPromiseTap,
    this.onProfileTap,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 18),
        decoration: BoxDecoration(
          color: _AppColors.backgroundLight.withValues(alpha: 0.92),
          border: Border(bottom: BorderSide(color: _AppColors.stone100)),
        ),
        child: SizedBox(
          height: 52,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      if (onBack != null) {
                        onBack!();
                      } else {
                        Navigator.of(context).pop();
                      }
                    },
                    child: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: _AppColors.stone100,
                      ),
                      child: const Icon(
                        CupertinoIcons.back,
                        size: 24,
                        color: _AppColors.textMain,
                      ),
                    ),
                  ),
                  const Spacer(),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onPromiseTap,
                    child: Container(
                      height: 40,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 10,
                      ),
                      decoration: BoxDecoration(
                        color: _AppColors.primary.withValues(alpha: 0.10),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Center(
                        child: Text(
                          '약속잡기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.primary,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onMore,
                    child: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: _AppColors.stone100,
                      ),
                      child: const Icon(
                        CupertinoIcons.ellipsis,
                        size: 24,
                        color: _AppColors.textMain,
                      ),
                    ),
                  ),
                ],
              ),
              Positioned.fill(
                child: Center(
                  child: GestureDetector(
                    behavior: HitTestBehavior.translucent,
                    onTap: onProfileTap,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 108),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                              height: 1.1,
                              letterSpacing: -0.3,
                              color: _AppColors.textMain,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            university,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              height: 1.1,
                              color: _AppColors.textSubtle,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActivePromiseBanner extends StatelessWidget {
  final Map<String, dynamic> activePromise;

  const _ActivePromiseBanner({required this.activePromise});

  String _formatTime(Timestamp? ts) {
    if (ts == null) return '';
    final dt = ts.toDate();
    final hour12 = dt.hour == 0 ? 12 : (dt.hour > 12 ? dt.hour - 12 : dt.hour);
    final minute = dt.minute.toString().padLeft(2, '0');
    final period = dt.hour >= 12 ? '오후' : '오전';
    return '${dt.month}월 ${dt.day}일 $period $hour12:$minute';
  }

  @override
  Widget build(BuildContext context) {
    final ts = activePromise['dateTime'] as Timestamp?;
    final place = activePromise['place']?.toString() ?? '';
    final category = activePromise['placeCategory']?.toString() ?? '';

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: _AppColors.primary.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _AppColors.primary.withValues(alpha: 0.20)),
      ),
      child: Text(
        '${_formatTime(ts)} · $category · $place 에 약속이 있어요',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: _AppColors.primary,
        ),
      ),
    );
  }
}

class _MessageItem extends StatelessWidget {
  final _ChatMessage message;
  final String avatarUrl;
  final VoidCallback? onApprovePromise;
  final VoidCallback? onRejectPromise;
  final VoidCallback? onEditPromise;
  final VoidCallback? onDeletePromise;
  final VoidCallback? onOpenProfile;

  const _MessageItem({
    required this.message,
    required this.avatarUrl,
    this.onApprovePromise,
    this.onRejectPromise,
    this.onEditPromise,
    this.onDeletePromise,
    this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    switch (message.type) {
      case MessageType.received:
        return _ReceivedMessage(
          text: message.text,
          time: message.time,
          avatarUrl: avatarUrl,
          onAvatarTap: onOpenProfile,
        );
      case MessageType.sent:
        return _SentMessage(
          text: message.text,
          time: message.time,
          isRead: message.isRead,
        );
      case MessageType.promiseRequest:
        return _PromiseRequestMessage(
          message: message,
          onApprove: onApprovePromise,
          onReject: onRejectPromise,
          onEdit: onEditPromise,
          onDelete: onDeletePromise,
        );
      case MessageType.promiseConfirmed:
        return _PromiseConfirmedBanner(
          message: message,
          onEdit: onEditPromise,
          onDelete: onDeletePromise,
        );
    }
  }
}

class _ReceivedMessage extends StatelessWidget {
  final String text;
  final String time;
  final String avatarUrl;
  final VoidCallback? onAvatarTap;

  const _ReceivedMessage({
    required this.text,
    required this.time,
    required this.avatarUrl,
    this.onAvatarTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onAvatarTap,
                child: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _AppColors.stone200,
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Image.network(
                    avatarUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const Icon(
                      CupertinoIcons.person_fill,
                      size: 20,
                      color: _AppColors.stone400,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.bubblePartner,
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(20),
                      topRight: Radius.circular(20),
                      bottomRight: Radius.circular(20),
                      bottomLeft: Radius.circular(4),
                    ),
                  ),
                  child: Text(
                    text,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 15,
                      height: 1.5,
                      color: _AppColors.textMain,
                    ),
                  ),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(left: 48, top: 4),
            child: Text(
              time,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 10,
                color: _AppColors.stone400,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SentMessage extends StatelessWidget {
  final String text;
  final String time;
  final bool isRead;

  const _SentMessage({
    required this.text,
    required this.time,
    this.isRead = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.75,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            decoration: BoxDecoration(
              color: _AppColors.bubbleUser,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(20),
                topRight: Radius.circular(20),
                bottomLeft: Radius.circular(20),
                bottomRight: Radius.circular(4),
              ),
              border: Border.all(color: const Color(0xFFEFECE8)),
            ),
            child: Text(
              text,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 15,
                height: 1.5,
                color: _AppColors.textMain,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(top: 4, right: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (isRead)
                  const Icon(
                    CupertinoIcons.checkmark_alt_circle_fill,
                    size: 12,
                    color: _AppColors.primary,
                  ),
                if (isRead) const SizedBox(width: 4),
                Text(
                  time,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 10,
                    color: _AppColors.stone400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PromiseRequestMessage extends StatelessWidget {
  final _ChatMessage message;
  final VoidCallback? onApprove;
  final VoidCallback? onReject;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  const _PromiseRequestMessage({
    required this.message,
    this.onApprove,
    this.onReject,
    this.onEdit,
    this.onDelete,
  });

  String _formatTime(DateTime? dateTime) {
    if (dateTime == null) return '';
    final hour12 = dateTime.hour == 0
        ? 12
        : (dateTime.hour > 12 ? dateTime.hour - 12 : dateTime.hour);
    final minute = dateTime.minute.toString().padLeft(2, '0');
    final period = dateTime.hour >= 12 ? '오후' : '오전';
    return '${dateTime.month}월 ${dateTime.day}일 $period $hour12:$minute';
  }

  @override
  Widget build(BuildContext context) {
    if (message.isExpired) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: CupertinoColors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: _AppColors.stone200),
          ),
          child: Column(
            children: [
              const Text(
                '약속 요청',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '${_formatTime(message.promiseDateTime)} · ${message.promiseCategory ?? ''} · ${message.promisePlace ?? ''}',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.textSubtle,
                ),
              ),
              if (message.isEdited && message.editedAt != null) ...[
                const SizedBox(height: 8),
                Text(
                  '약속이 수정되었어요 (${_formatTime(message.editedAt)})',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.primary,
                  ),
                ),
              ],
              const SizedBox(height: 10),
              Text(
                message.text,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 13,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 14),
              if (message.promiseStatus == 'cancelled')
                const Text(
                  '삭제된 약속이에요.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    color: _AppColors.textSubtle,
                  ),
                )
              else if (!message.isMineRequest)
                Row(
                  children: [
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: onReject,
                        child: Container(
                          height: 42,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: _AppColors.stone100,
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: const Text(
                            '거절',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontWeight: FontWeight.w700,
                              color: _AppColors.textMain,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: onApprove,
                        child: Container(
                          height: 42,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: const Text(
                            '승인',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                )
              else
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text(
                      '상대방의 응답을 기다리는 중...',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        color: _AppColors.textSubtle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: onEdit,
                      child: const Text(
                        '수정',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.primary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: onDelete,
                      child: const Text(
                        '삭제',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: CupertinoColors.systemRed,
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PromiseConfirmedBanner extends StatelessWidget {
  final _ChatMessage message;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  const _PromiseConfirmedBanner({
    required this.message,
    this.onEdit,
    this.onDelete,
  });

  String _formatTime(DateTime? dateTime) {
    if (dateTime == null) return '';
    final hour12 = dateTime.hour == 0
        ? 12
        : (dateTime.hour > 12 ? dateTime.hour - 12 : dateTime.hour);
    final minute = dateTime.minute.toString().padLeft(2, '0');
    final period = dateTime.hour >= 12 ? '오후' : '오전';
    return '${dateTime.month}월 ${dateTime.day}일 $period $hour12:$minute';
  }

  @override
  Widget build(BuildContext context) {
    if (message.isExpired) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: _AppColors.primary.withValues(alpha: 0.10),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _AppColors.primary.withValues(alpha: 0.25),
            ),
          ),
          child: Column(
            children: [
              const Text(
                '약속 확정',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: _AppColors.primary,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '${_formatTime(message.promiseDateTime)} · ${message.promiseCategory ?? ''} · ${message.promisePlace ?? ''}',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.textMain,
                ),
              ),
              if (message.isEdited && message.editedAt != null) ...[
                const SizedBox(height: 8),
                Text(
                  '약속이 수정되었어요 (${_formatTime(message.editedAt)})',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.primary,
                  ),
                ),
              ],
              const SizedBox(height: 10),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onEdit,
                    child: const Text(
                      '약속 수정',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.primary,
                      ),
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onDelete,
                    child: const Text(
                      '삭제',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.systemRed,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PromiseFormResult {
  final DateTime dateTime;
  final String place;
  final String placeCategory;

  const _PromiseFormResult({
    required this.dateTime,
    required this.place,
    required this.placeCategory,
  });
}

class _PromiseCreateBottomSheet extends StatefulWidget {
  final DateTime? initialDateTime;
  final String? initialCategory;
  final String? initialPlace;

  const _PromiseCreateBottomSheet({
    this.initialDateTime,
    this.initialCategory,
    this.initialPlace,
  });

  @override
  State<_PromiseCreateBottomSheet> createState() =>
      _PromiseCreateBottomSheetState();
}

class _PromiseCreateBottomSheetState extends State<_PromiseCreateBottomSheet> {
  late DateTime selectedDate;
  late String selectedPeriod;
  late TextEditingController hourController;
  late TextEditingController minuteController;

  String selectedCategory = '카페';
  String selectedPlace = '스타벅스 신촌점';

  final Map<String, List<String>> placesByCategory = const {
    '식당': ['연남 파스타집', '신촌 삼겹살집', '홍대 덮밥집', '이대 초밥집'],
    '카페': ['스타벅스 신촌점', '투썸플레이스 연세로점', '블루보틀 성수점', '조용한 개인카페'],
    '바': ['와인바 연남', '칵테일바 신촌', '하이볼바 성수', '루프탑 바'],
    '야외': ['한강공원 여의도', '서울숲', '연트럴파크', '남산 산책로'],
    '이색 장소': ['보드게임카페', '방탈출카페', '전시회', '소품샵 거리'],
  };

  List<String> get categories => placesByCategory.keys.toList();
  List<String> get currentPlaces =>
      placesByCategory[selectedCategory] ?? const [];

  @override
  void initState() {
    super.initState();

    final initialDt =
        widget.initialDateTime ?? DateTime.now().add(const Duration(days: 1));
    selectedDate = DateTime(initialDt.year, initialDt.month, initialDt.day);

    final hour12 = initialDt.hour == 0
        ? 12
        : (initialDt.hour > 12 ? initialDt.hour - 12 : initialDt.hour);
    selectedPeriod = initialDt.hour >= 12 ? '오후' : '오전';
    hourController = TextEditingController(text: '$hour12');
    minuteController = TextEditingController(
      text: initialDt.minute.toString().padLeft(2, '0'),
    );

    if (widget.initialCategory != null &&
        placesByCategory.containsKey(widget.initialCategory)) {
      selectedCategory = widget.initialCategory!;
    }

    if (widget.initialPlace != null &&
        (placesByCategory[selectedCategory]?.contains(widget.initialPlace) ??
            false)) {
      selectedPlace = widget.initialPlace!;
    } else {
      selectedPlace = placesByCategory[selectedCategory]!.first;
    }
  }

  @override
  void dispose() {
    hourController.dispose();
    minuteController.dispose();
    super.dispose();
  }

  DateTime get selectedDateTime {
    final rawHour = int.tryParse(hourController.text.trim()) ?? 12;
    final rawMinute = int.tryParse(minuteController.text.trim()) ?? 0;

    final clampedHour = rawHour.clamp(1, 12);
    final clampedMinute = rawMinute.clamp(0, 59);

    int hour24;
    if (selectedPeriod == '오전') {
      hour24 = clampedHour == 12 ? 0 : clampedHour;
    } else {
      hour24 = clampedHour == 12 ? 12 : clampedHour + 12;
    }

    return DateTime(
      selectedDate.year,
      selectedDate.month,
      selectedDate.day,
      hour24,
      clampedMinute,
    );
  }

  void _showValidationDialog(String message) {
    showCupertinoDialog(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        title: const Text('시간 확인'),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            child: const Text('확인'),
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final previewHour = (int.tryParse(hourController.text.trim()) ?? 12).clamp(
      1,
      12,
    );
    final previewMinute = (int.tryParse(minuteController.text.trim()) ?? 0)
        .clamp(0, 59);

    return Align(
      alignment: Alignment.bottomCenter,
      child: Container(
        height: MediaQuery.of(context).size.height * 0.82,
        decoration: const BoxDecoration(
          color: CupertinoColors.systemBackground,
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                  color: _AppColors.stone200,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                '약속 잡기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 16),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '날짜 선택',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Container(
                        decoration: BoxDecoration(
                          color: CupertinoColors.white,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: _AppColors.stone100),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(20),
                          child: material.Material(
                            type: material.MaterialType.transparency,
                            child: material.CalendarDatePicker(
                              initialDate: selectedDate,
                              firstDate: DateTime.now(),
                              lastDate: DateTime.now().add(
                                const Duration(days: 180),
                              ),
                              onDateChanged: (value) {
                                setState(() {
                                  selectedDate = value;
                                });
                              },
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        '약속 시각',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 20,
                        ),
                        decoration: BoxDecoration(
                          color: CupertinoColors.white,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: _AppColors.stone100),
                        ),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                _PeriodButton(
                                  label: '오전',
                                  isSelected: selectedPeriod == '오전',
                                  onTap: () =>
                                      setState(() => selectedPeriod = '오전'),
                                ),
                                const SizedBox(width: 8),
                                _PeriodButton(
                                  label: '오후',
                                  isSelected: selectedPeriod == '오후',
                                  onTap: () =>
                                      setState(() => selectedPeriod = '오후'),
                                ),
                              ],
                            ),
                            const SizedBox(height: 16),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                SizedBox(
                                  width: 88,
                                  child: CupertinoTextField(
                                    controller: hourController,
                                    keyboardType: TextInputType.number,
                                    textAlign: TextAlign.center,
                                    maxLength: 2,
                                    placeholder: '12',
                                    style: const TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 36,
                                      fontWeight: FontWeight.w800,
                                      color: _AppColors.textMain,
                                    ),
                                    placeholderStyle: const TextStyle(
                                      fontSize: 36,
                                      fontWeight: FontWeight.w800,
                                      color: _AppColors.stone400,
                                    ),
                                    padding: const EdgeInsets.symmetric(
                                      vertical: 14,
                                    ),
                                    decoration: BoxDecoration(
                                      color: _AppColors.stone100,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    onChanged: (_) => setState(() {}),
                                  ),
                                ),
                                const Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 10),
                                  child: Text(
                                    ':',
                                    style: TextStyle(
                                      fontSize: 40,
                                      fontWeight: FontWeight.w800,
                                      color: _AppColors.textMain,
                                    ),
                                  ),
                                ),
                                SizedBox(
                                  width: 88,
                                  child: CupertinoTextField(
                                    controller: minuteController,
                                    keyboardType: TextInputType.number,
                                    textAlign: TextAlign.center,
                                    maxLength: 2,
                                    placeholder: '00',
                                    style: const TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 36,
                                      fontWeight: FontWeight.w800,
                                      color: _AppColors.textMain,
                                    ),
                                    placeholderStyle: const TextStyle(
                                      fontSize: 36,
                                      fontWeight: FontWeight.w800,
                                      color: _AppColors.stone400,
                                    ),
                                    padding: const EdgeInsets.symmetric(
                                      vertical: 14,
                                    ),
                                    decoration: BoxDecoration(
                                      color: _AppColors.stone100,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    onChanged: (_) => setState(() {}),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            const Text(
                              '시: 1~12 / 분: 0~59 로 입력',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 12,
                                color: _AppColors.textSubtle,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        '장소 카테고리',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 10),
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: categories.map((category) {
                            final isSelected = selectedCategory == category;
                            return Padding(
                              padding: const EdgeInsets.only(right: 8),
                              child: CupertinoButton(
                                padding: EdgeInsets.zero,
                                onPressed: () {
                                  setState(() {
                                    selectedCategory = category;
                                    selectedPlace =
                                        placesByCategory[category]!.first;
                                  });
                                },
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 10,
                                  ),
                                  decoration: BoxDecoration(
                                    color: isSelected
                                        ? _AppColors.primary.withValues(
                                            alpha: 0.10,
                                          )
                                        : CupertinoColors.white,
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(
                                      color: isSelected
                                          ? _AppColors.primary
                                          : _AppColors.stone100,
                                    ),
                                  ),
                                  child: Text(
                                    category,
                                    style: TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 13,
                                      fontWeight: FontWeight.w700,
                                      color: isSelected
                                          ? _AppColors.primary
                                          : _AppColors.textMain,
                                    ),
                                  ),
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        '장소 선택',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 10),
                      ...currentPlaces.map(
                        (place) => Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: () {
                              setState(() {
                                selectedPlace = place;
                              });
                            },
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 16,
                              ),
                              decoration: BoxDecoration(
                                color: selectedPlace == place
                                    ? _AppColors.primary.withValues(alpha: 0.08)
                                    : CupertinoColors.white,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: selectedPlace == place
                                      ? _AppColors.primary
                                      : _AppColors.stone100,
                                ),
                              ),
                              child: Text(
                                place,
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                  color: selectedPlace == place
                                      ? _AppColors.primary
                                      : _AppColors.textMain,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: _AppColors.stone100,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Text(
                          '선택한 일정\n'
                          '${selectedDate.month}월 ${selectedDate.day}일 '
                          '$selectedPeriod ${previewHour.toString().padLeft(2, '0')} : ${previewMinute.toString().padLeft(2, '0')}\n'
                          '$selectedCategory · $selectedPlace',
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 13,
                            height: 1.5,
                            color: _AppColors.textMain,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                child: Row(
                  children: [
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => Navigator.pop(context),
                        child: Container(
                          height: 52,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: _AppColors.stone100,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            '취소',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.textMain,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          final hour = int.tryParse(hourController.text.trim());
                          final minute = int.tryParse(
                            minuteController.text.trim(),
                          );

                          if (hour == null || hour < 1 || hour > 12) {
                            _showValidationDialog('시는 1부터 12까지 입력해주세요.');
                            return;
                          }
                          if (minute == null || minute < 0 || minute > 59) {
                            _showValidationDialog('분은 0부터 59까지 입력해주세요.');
                            return;
                          }

                          Navigator.pop(
                            context,
                            _PromiseFormResult(
                              dateTime: selectedDateTime,
                              place: selectedPlace,
                              placeCategory: selectedCategory,
                            ),
                          );
                        },
                        child: Container(
                          height: 52,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Text(
                            '약속 요청 보내기',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PeriodButton extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _PeriodButton({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected
              ? _AppColors.primary.withValues(alpha: 0.10)
              : CupertinoColors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected ? _AppColors.primary : _AppColors.stone100,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: isSelected ? _AppColors.primary : _AppColors.textMain,
          ),
        ),
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final double bottomPadding;
  final VoidCallback? onSend;

  const _InputBar({
    required this.controller,
    required this.bottomPadding,
    this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottomPadding + 32),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight.withValues(alpha: 0.9),
            _AppColors.backgroundLight,
          ],
        ),
      ),
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 4, 8, 4),
        decoration: BoxDecoration(
          color: CupertinoColors.white,
          borderRadius: BorderRadius.circular(32),
          border: Border.all(color: _AppColors.stone100),
        ),
        child: Row(
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {},
              child: Transform.rotate(
                angle: 0.785,
                child: const Icon(
                  CupertinoIcons.paperclip,
                  size: 24,
                  color: _AppColors.stone400,
                ),
              ),
            ),
            Expanded(
              child: CupertinoTextField(
                controller: controller,
                placeholder: 'Write a message...',
                placeholderStyle: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  color: _AppColors.stone400,
                ),
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  color: _AppColors.textMain,
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 12,
                ),
                decoration: null,
                onSubmitted: (_) => onSend?.call(),
              ),
            ),
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                HapticFeedback.mediumImpact();
                onSend?.call();
              },
              child: Container(
                width: 40,
                height: 40,
                decoration: const BoxDecoration(
                  color: _AppColors.sendButton,
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  CupertinoIcons.paperplane_fill,
                  size: 20,
                  color: CupertinoColors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
