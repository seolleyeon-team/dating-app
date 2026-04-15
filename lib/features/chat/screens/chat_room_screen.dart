import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter/services.dart';

import '../models/promise_place.dart';
import '../services/chat_service.dart';
import '../services/promise_place_service.dart';
import '../utils/safety_stamp_availability.dart';
import '../widgets/promise_place_picker_sheet.dart';
import 'safety_stamp_screen.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../services/push_notification_service.dart';
import '../../../router/route_names.dart';
import '../../matching/models/profile_card_args.dart';

class _AppColors {
  /// 라벤더 포인트 (#c6a9fe 계열) — 본문/선택 상태 (대비용으로 소프트보다 진함)
  static const Color primary = Color(0xFF9B7FD8);

  /// 사용자 지정 라벤더 #c6a9fe — 칩·배너·연한 배경
  static const Color primarySoft = Color(0xFFC6A9FE);

  /// 연한 보라 채우기용 알파 (버튼·칩 배경 — 약 30% 더 연하게 조정 시 배수)
  static const double promiseFillAlpha = 0.29;
  static const double promiseFillAlphaLight = 0.25;
  static const double promiseBorderAlpha = 0.39;
  static const double promiseBorderAlphaStrong = 0.43;
  static const Color backgroundLight = Color(0xFFFAFAFC);
  static const Color bubbleUser = Color(0xFFF5F2EE);
  static const Color bubblePartner = Color(0xFFF0F3F5);
  static const Color textMain = Color(0xFF201F1D);
  static const Color textSubtle = Color(0xFF868E96);
  static const Color stone100 = Color(0xFFF5F5F4);
  static const Color stone200 = Color(0xFFE7E5E4);
  static const Color stone400 = Color(0xFFA8A29E);
  static const Color sendButton = Color(0xFFFFB2C1);
}

enum MessageType {
  received,
  sent,
  promiseRequest,
  promiseConfirmed,
  promiseInProgress,
  promiseCompleted,
}

double? _readFirestoreDouble(dynamic v) {
  if (v is num) return v.toDouble();
  return double.tryParse(v?.toString() ?? '');
}

String _promiseDetailSubtitle({
  required DateTime? dateTime,
  required String? category,
  required String? place,
  required String Function(DateTime? d) formatDt,
}) {
  final cat = PromisePlaceCategory.labelOrEmpty(category ?? '');
  final pl = place ?? '';
  final tm = formatDt(dateTime);
  final parts = <String>[];
  if (tm.isNotEmpty) parts.add(tm);
  if (cat.isNotEmpty) parts.add(cat);
  if (pl.isNotEmpty) parts.add(pl);
  return parts.join(' · ');
}

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
  final String? promisePlaceId;
  final String? promisePlaceAddress;
  final double? promisePlaceLat;
  final double? promisePlaceLng;
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
    this.promisePlaceId,
    this.promisePlaceAddress,
    this.promisePlaceLat,
    this.promisePlaceLng,
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

  bool get shouldHideAsExpired {
    return type == MessageType.promiseRequest &&
        promiseStatus == 'requested' &&
        isExpired;
  }

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
    String? promisePlaceId,
    String? promisePlaceAddress,
    double? promisePlaceLat,
    double? promisePlaceLng,
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
      promisePlaceId: promisePlaceId ?? this.promisePlaceId,
      promisePlaceAddress: promisePlaceAddress ?? this.promisePlaceAddress,
      promisePlaceLat: promisePlaceLat ?? this.promisePlaceLat,
      promisePlaceLng: promisePlaceLng ?? this.promisePlaceLng,
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
  static const double _topAreaHeight = 232;

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
  bool _isNearBottom = true;
  bool _pendingForceScrollToBottom = true;
  bool _isCancellingExpiredPromise = false;
  DateTime _currentNow = DateTime.now();
  Timer? _safetyStampTimer;
  String? _lastMessageSnapshotSignature;

  void _openPartnerProfileCard() {
    if (widget.partnerId.isEmpty) return;

    Navigator.of(context, rootNavigator: true).pushNamed(
      RouteNames.profileSpecificDetail,
      arguments: ProfileCardArgs.fromChat(userId: widget.partnerId),
    );
  }

  void _startSafetyStampTimer() {
    _safetyStampTimer?.cancel();
    _safetyStampTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!mounted) return;
      setState(() {
        _currentNow = DateTime.now();
      });
    });
  }

  void _openSafetyStampScreen(Map<String, dynamic>? activePromise) {
    final availability = evaluateSafetyStampAvailability(
      activePromise,
      now: _currentNow,
    );
    if (!availability.canOpen) {
      showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('안전도장을 열 수 없어요'),
          content: Text(availability.message),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
      return;
    }

    Navigator.of(context).push(
      CupertinoPageRoute<void>(
        builder: (_) => SafetyStampScreen(
          roomId: _roomId,
          promiseId: activePromise?['promiseId']?.toString() ?? '',
          currentUserId: _currentUserId ?? '',
          partnerId: widget.partnerId,
          partnerName: widget.partnerName.isEmpty ? '상대방' : widget.partnerName,
          myName: _currentUserName.isEmpty ? '나' : _currentUserName,
        ),
      ),
    );
  }

  Future<void> _cancelExpiredPromiseIfNeeded(
    Map<String, dynamic>? activePromise,
  ) async {
    if (_isCancellingExpiredPromise ||
        activePromise == null ||
        _roomId.isEmpty) {
      return;
    }
    if (!isMeetupSafetyStampExpired(activePromise, now: _currentNow)) {
      return;
    }

    final promiseId = activePromise['promiseId']?.toString() ?? '';
    if (promiseId.isEmpty) return;

    _isCancellingExpiredPromise = true;
    try {
      await _chatService.cancelExpiredIncompleteSafetyStamp(
        roomId: _roomId,
        promiseId: promiseId,
      );
    } finally {
      _isCancellingExpiredPromise = false;
    }
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScrollChanged);
    _startSafetyStampTimer();
    _initChat();
  }

  @override
  void dispose() {
    if (_roomId.isNotEmpty) {
      PushNotificationService.instance.clearOpenedChatRoom(_roomId);
    }
    _safetyStampTimer?.cancel();
    _messageController.dispose();
    _scrollController.removeListener(_handleScrollChanged);
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

  void _handleScrollChanged() {
    if (!_scrollController.hasClients) return;

    final position = _scrollController.position;
    final distanceFromBottom = position.maxScrollExtent - position.pixels;
    _isNearBottom = distanceFromBottom <= 96;
  }

  void _maybeAutoScrollToBottom(
    List<QueryDocumentSnapshot<Map<String, dynamic>>> messageDocs,
  ) {
    final lastMessageId = messageDocs.isEmpty ? 'empty' : messageDocs.last.id;
    final nextSignature = '${messageDocs.length}:$lastMessageId';
    final hasSnapshotChanged = nextSignature != _lastMessageSnapshotSignature;

    if (_lastMessageSnapshotSignature == null) {
      _lastMessageSnapshotSignature = nextSignature;
      _pendingForceScrollToBottom = false;
      _scrollToBottom();
      return;
    }

    _lastMessageSnapshotSignature = nextSignature;

    if (!hasSnapshotChanged) return;
    if (!_pendingForceScrollToBottom && !_isNearBottom) return;

    _pendingForceScrollToBottom = false;
    _scrollToBottom();
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
      _pendingForceScrollToBottom = true;

      await _chatService.sendTextMessage(
        roomId: _roomId,
        senderId: _currentUserId!,
        text: text,
      );

      widget.onSend?.call(text);
      _scrollToBottom();
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      } else {
        _isSending = false;
      }
    }
  }

  Future<void> _openPromiseSheet({
    String? editingPromiseId,
    DateTime? initialDateTime,
    String? initialCategory,
    String? initialPlace,
    String? initialPlaceId,
  }) async {
    if (_currentUserId == null || _roomId.isEmpty) return;

    final result = await showCupertinoModalPopup<_PromiseFormResult>(
      context: context,
      builder: (context) => _PromiseCreateBottomSheet(
        initialDateTime: initialDateTime,
        initialCategory: initialCategory,
        initialPlace: initialPlace,
        initialPlaceId: initialPlaceId,
      ),
    );

    if (result == null) return;

    try {
      if (editingPromiseId != null) {
        await _chatService.updatePromise(
          roomId: _roomId,
          promiseId: editingPromiseId,
          editedBy: _currentUserId!,
          dateTime: result.dateTime,
          place: result.place,
          placeCategory: result.placeCategory,
          placeId: result.placeId,
          placeAddress: result.placeAddress,
          placeLat: result.placeLat,
          placeLng: result.placeLng,
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
        placeId: result.placeId,
        placeAddress: result.placeAddress,
        placeLat: result.placeLat,
        placeLng: result.placeLng,
      );
    } catch (e) {
      if (!mounted) return;
      await showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('약속 요청을 보내지 못했어요'),
          content: Text(
            '저장 중 문제가 생겼어요. Firestore 규칙과 네트워크 상태를 확인한 뒤 다시 시도해주세요.\n\n$e',
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
    }
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
        promisePlaceId: data['placeId']?.toString(),
        promisePlaceAddress: data['placeAddress']?.toString(),
        promisePlaceLat: _readFirestoreDouble(data['placeLat']),
        promisePlaceLng: _readFirestoreDouble(data['placeLng']),
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
        promisePlaceId: data['placeId']?.toString(),
        promisePlaceAddress: data['placeAddress']?.toString(),
        promisePlaceLat: _readFirestoreDouble(data['placeLat']),
        promisePlaceLng: _readFirestoreDouble(data['placeLng']),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: promiseStatus ?? 'confirmed',
        isEdited: isEdited,
        editedAt: editedAt,
      );
    }

    if (type == 'promise_in_progress') {
      return _ChatMessage(
        type: MessageType.promiseInProgress,
        text: text.isNotEmpty ? text : '약속을 진행중입니다',
        time: '',
        sortDateTime: createdAt,
        promiseId: data['promiseId']?.toString(),
        promiseDateTime: promiseDateTime,
        promisePlace: data['place']?.toString(),
        promiseCategory: data['placeCategory']?.toString(),
        promisePlaceId: data['placeId']?.toString(),
        promisePlaceAddress: data['placeAddress']?.toString(),
        promisePlaceLat: _readFirestoreDouble(data['placeLat']),
        promisePlaceLng: _readFirestoreDouble(data['placeLng']),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: promiseStatus ?? 'in_progress',
        isEdited: false,
        editedAt: editedAt,
      );
    }

    if (type == 'promise_completed') {
      return _ChatMessage(
        type: MessageType.promiseCompleted,
        text: text.isNotEmpty ? text : '약속이 완료되었어요',
        time: '',
        sortDateTime: createdAt,
        promiseId: data['promiseId']?.toString(),
        promiseDateTime: promiseDateTime,
        promisePlace: data['place']?.toString(),
        promiseCategory: data['placeCategory']?.toString(),
        promisePlaceId: data['placeId']?.toString(),
        promisePlaceAddress: data['placeAddress']?.toString(),
        promisePlaceLat: _readFirestoreDouble(data['placeLat']),
        promisePlaceLng: _readFirestoreDouble(data['placeLng']),
        isMineRequest: senderId == _currentUserId,
        promiseStatus: promiseStatus ?? 'completed',
        isEdited: false,
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
        promisePlaceId: data['placeId']?.toString(),
        promisePlaceAddress: data['placeAddress']?.toString(),
        promisePlaceLat: _readFirestoreDouble(data['placeLat']),
        promisePlaceLng: _readFirestoreDouble(data['placeLng']),
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
        if (message.promiseStatus != 'rejected' &&
            !message.shouldHideAsExpired) {
          normalMessages.add(message);
        }
        continue;
      }

      if (message.promiseStatus == 'rejected' || message.shouldHideAsExpired) {
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
        type:
            message.type == MessageType.promiseConfirmed ||
                message.type == MessageType.promiseInProgress
            ? message.type
            : existing.type,
        text:
            message.type == MessageType.promiseConfirmed ||
                message.type == MessageType.promiseInProgress
            ? message.text
            : existing.text,
        promiseDateTime: message.promiseDateTime ?? existing.promiseDateTime,
        promisePlace: message.promisePlace ?? existing.promisePlace,
        promiseCategory: message.promiseCategory ?? existing.promiseCategory,
        promisePlaceId: message.promisePlaceId ?? existing.promisePlaceId,
        promisePlaceAddress:
            message.promisePlaceAddress ?? existing.promisePlaceAddress,
        promisePlaceLat: message.promisePlaceLat ?? existing.promisePlaceLat,
        promisePlaceLng: message.promisePlaceLng ?? existing.promisePlaceLng,
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

                          _maybeAutoScrollToBottom(messageDocs);

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
                                  initialPlaceId: message.promisePlaceId,
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
                _cancelExpiredPromiseIfNeeded(activePromise);
                final safetyStampPhase = activePromise == null
                    ? null
                    : deriveSafetyStampPhase(activePromise);
                final promiseTime = activePromise == null
                    ? null
                    : parsePromiseDateTime(activePromise['dateTime']);
                final isPromiseWithinVisibleWindow =
                    promiseTime != null &&
                    !_currentNow.isAfter(
                      promiseTime.add(const Duration(hours: 1)),
                    );
                final shouldShowSafetyStampButton =
                    activePromise != null &&
                    isPromiseWithinVisibleWindow &&
                    safetyStampPhase != SafetyStampPhase.completed;
                final shouldShowActivePromiseBanner =
                    activePromise != null &&
                    isPromiseWithinVisibleWindow &&
                    safetyStampPhase == SafetyStampPhase.meetup;
                final safetyStampAvailability = evaluateSafetyStampAvailability(
                  activePromise,
                  now: _currentNow,
                );

                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _Header(
                      name: widget.partnerName,
                      university: widget.partnerUniversity,
                      onBack: widget.onBack,
                      onMore: widget.onMore,
                      onPromiseTap: () => _openPromiseSheet(),
                      onProfileTap: _openPartnerProfileCard,
                    ),
                    _SafetyStampEntryButton(
                      isVisible: shouldShowSafetyStampButton,
                      isEnabled: safetyStampAvailability.canOpen,
                      helperText: safetyStampAvailability.message,
                      onTap: () => _openSafetyStampScreen(activePromise),
                    ),
                    if (shouldShowActivePromiseBanner)
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

class _SafetyStampEntryButton extends StatelessWidget {
  final bool isVisible;
  final bool isEnabled;
  final String helperText;
  final VoidCallback onTap;

  const _SafetyStampEntryButton({
    required this.isVisible,
    required this.isEnabled,
    required this.helperText,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (!isVisible) return const SizedBox.shrink();

    final backgroundColor = isEnabled
        ? const Color(0xFFFFF3F6)
        : const Color(0xFFF7F5F3);
    final borderColor = isEnabled
        ? const Color(0xFFF4C6D2)
        : const Color(0xFFE6E1DC);
    final iconColor = isEnabled
        ? const Color(0xFFEF6C93)
        : const Color(0xFFB7AEA6);
    final titleColor = isEnabled
        ? const Color(0xFFB94D72)
        : const Color(0xFF8F867E);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: borderColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    CupertinoIcons.checkmark_seal_fill,
                    size: 18,
                    color: iconColor,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      '안전도장으로 이동하기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: titleColor,
                      ),
                    ),
                  ),
                  Icon(
                    CupertinoIcons.right_chevron,
                    size: 16,
                    color: titleColor,
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                helperText,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: _AppColors.textSubtle,
                  height: 1.35,
                ),
              ),
            ],
          ),
        ),
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
          child: Row(
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
              Expanded(
                child: Align(
                  alignment: Alignment.center,
                  child: GestureDetector(
                    behavior: HitTestBehavior.deferToChild,
                    onTap: onProfileTap,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          maxWidth: MediaQuery.sizeOf(context).width * 0.42,
                        ),
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
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: onPromiseTap,
                child: Container(
                  height: 40,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primarySoft.withValues(
                      alpha: _AppColors.promiseFillAlpha,
                    ),
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
    final categoryRaw = activePromise['placeCategory']?.toString() ?? '';
    final categoryLabel = PromisePlaceCategory.labelOrEmpty(categoryRaw);

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: _AppColors.primarySoft.withValues(
          alpha: _AppColors.promiseFillAlphaLight,
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: _AppColors.primarySoft.withValues(
            alpha: _AppColors.promiseBorderAlpha,
          ),
        ),
      ),
      child: Text(
        '${_formatTime(ts)}${categoryLabel.isEmpty ? '' : ' · $categoryLabel'} · $place 에 약속이 있어요',
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
      case MessageType.promiseInProgress:
        return _PromiseInProgressBanner(message: message);
      case MessageType.promiseCompleted:
        return _PromiseCompletedBanner(message: message);
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
    if (message.shouldHideAsExpired) return const SizedBox.shrink();

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
                _promiseDetailSubtitle(
                  dateTime: message.promiseDateTime,
                  category: message.promiseCategory,
                  place: message.promisePlace,
                  formatDt: _formatTime,
                ),
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
    if (message.shouldHideAsExpired) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: _AppColors.primarySoft.withValues(
              alpha: _AppColors.promiseFillAlpha,
            ),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _AppColors.primarySoft.withValues(
                alpha: _AppColors.promiseBorderAlphaStrong,
              ),
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
                _promiseDetailSubtitle(
                  dateTime: message.promiseDateTime,
                  category: message.promiseCategory,
                  place: message.promisePlace,
                  formatDt: _formatTime,
                ),
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

class _PromiseCompletedBanner extends StatelessWidget {
  final _ChatMessage message;

  const _PromiseCompletedBanner({required this.message});

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
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFEAF5EE),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFFC7E5D0)),
          ),
          child: Column(
            children: [
              const Text(
                '약속 완료',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF2E7D4F),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _promiseDetailSubtitle(
                  dateTime: message.promiseDateTime,
                  category: message.promiseCategory,
                  place: message.promisePlace,
                  formatDt: _formatTime,
                ),
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                '약속이 완료되었어요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF2E7D4F),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PromiseInProgressBanner extends StatelessWidget {
  final _ChatMessage message;

  const _PromiseInProgressBanner({required this.message});

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
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF7E8),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFFF0D7A6)),
          ),
          child: Column(
            children: [
              const Text(
                '약속 진행중',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF9A6500),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _promiseDetailSubtitle(
                  dateTime: message.promiseDateTime,
                  category: message.promiseCategory,
                  place: message.promisePlace,
                  formatDt: _formatTime,
                ),
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                '약속을 진행중입니다',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF9A6500),
                ),
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
  final String? placeId;
  final String? placeAddress;
  final double? placeLat;
  final double? placeLng;

  const _PromiseFormResult({
    required this.dateTime,
    required this.place,
    required this.placeCategory,
    this.placeId,
    this.placeAddress,
    this.placeLat,
    this.placeLng,
  });
}

class _PromiseCreateBottomSheet extends StatefulWidget {
  final DateTime? initialDateTime;
  final String? initialCategory;
  final String? initialPlace;
  final String? initialPlaceId;

  const _PromiseCreateBottomSheet({
    this.initialDateTime,
    this.initialCategory,
    this.initialPlace,
    this.initialPlaceId,
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
  late FocusNode _hourFocusNode;
  late FocusNode _minuteFocusNode;

  final PromisePlaceService _placeService = PromisePlaceService();
  PromisePlace? _selectedPlace;
  bool _placesLoading = true;

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
    _hourFocusNode = FocusNode()..addListener(_handleTimeFieldFocusChanged);
    _minuteFocusNode = FocusNode()..addListener(_handleTimeFieldFocusChanged);

    _bootstrapSelectedPlace();
  }

  void _handleTimeFieldFocusChanged() {
    if (!mounted) return;
    setState(() {});
  }

  Future<void> _bootstrapSelectedPlace() async {
    final list = await _placeService.loadPlaces();
    if (!mounted) return;

    PromisePlace? selected;
    final id = widget.initialPlaceId;
    if (id != null && id.isNotEmpty) {
      for (final p in list) {
        if (p.placeId == id) {
          selected = p;
          break;
        }
      }
    }
    if (selected == null) {
      final name = widget.initialPlace;
      if (name != null && name.isNotEmpty) {
        for (final p in list) {
          if (p.name == name) {
            selected = p;
            break;
          }
        }
      }
    }
    if (selected == null) {
      final cat = widget.initialCategory;
      final isLikelyEdit =
          (widget.initialPlaceId != null &&
              widget.initialPlaceId!.isNotEmpty) ||
          (widget.initialPlace != null && widget.initialPlace!.isNotEmpty);
      if (isLikelyEdit && cat != null && cat.isNotEmpty) {
        final want = PromisePlaceCategory.normalize(cat);
        final inCat = list.where((e) => e.category == want).toList();
        if (inCat.isNotEmpty) selected = inCat.first;
      }
    }

    setState(() {
      _selectedPlace = selected;
      _placesLoading = false;
    });
  }

  @override
  void dispose() {
    _hourFocusNode
      ..removeListener(_handleTimeFieldFocusChanged)
      ..dispose();
    _minuteFocusNode
      ..removeListener(_handleTimeFieldFocusChanged)
      ..dispose();
    hourController.dispose();
    minuteController.dispose();
    super.dispose();
  }

  bool get _isEditingTime =>
      _hourFocusNode.hasFocus || _minuteFocusNode.hasFocus;

  void _dismissKeyboard() {
    final currentFocus = FocusScope.of(context);
    if (!currentFocus.hasPrimaryFocus) {
      currentFocus.unfocus();
    }
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

  void _showValidationDialog(String message, {String title = '시간 확인'}) {
    showCupertinoDialog(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        title: Text(title),
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
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _dismissKeyboard,
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
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
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
                              child: material.Theme(
                                data: material.ThemeData(
                                  useMaterial3: true,
                                  colorScheme: material.ColorScheme.light(
                                    primary: _AppColors.primary,
                                    onPrimary: const Color(0xFFFFFFFF),
                                    surface: const Color(0xFFFFFFFF),
                                  ),
                                  datePickerTheme: material.DatePickerThemeData(
                                    todayForegroundColor:
                                        material
                                            .WidgetStateProperty.resolveWith((
                                          states,
                                        ) {
                                          if (states.contains(
                                            material.WidgetState.selected,
                                          )) {
                                            return const Color(0xFFFFFFFF);
                                          }
                                          return _AppColors.primary;
                                        }),
                                    todayBackgroundColor:
                                        material
                                            .WidgetStateProperty.resolveWith((
                                          states,
                                        ) {
                                          if (states.contains(
                                            material.WidgetState.selected,
                                          )) {
                                            return _AppColors.primary;
                                          }
                                          return _AppColors.primarySoft
                                              .withValues(alpha: 0.22);
                                        }),
                                  ),
                                ),
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
                                      focusNode: _hourFocusNode,
                                      keyboardType: TextInputType.number,
                                      textInputAction: TextInputAction.next,
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
                                      onSubmitted: (_) {
                                        _minuteFocusNode.requestFocus();
                                      },
                                    ),
                                  ),
                                  const Padding(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: 10,
                                    ),
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
                                      focusNode: _minuteFocusNode,
                                      keyboardType: TextInputType.number,
                                      textInputAction: TextInputAction.done,
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
                                      onSubmitted: (_) => _dismissKeyboard(),
                                    ),
                                  ),
                                ],
                              ),
                              if (_isEditingTime) ...[
                                const SizedBox(height: 12),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: CupertinoButton(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 14,
                                      vertical: 8,
                                    ),
                                    minimumSize: Size.zero,
                                    onPressed: _dismissKeyboard,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 14,
                                        vertical: 8,
                                      ),
                                      decoration: BoxDecoration(
                                        color: _AppColors.primarySoft
                                            .withValues(
                                              alpha:
                                                  _AppColors.promiseFillAlpha,
                                            ),
                                        borderRadius: BorderRadius.circular(
                                          999,
                                        ),
                                        border: Border.all(
                                          color: _AppColors.primarySoft,
                                        ),
                                      ),
                                      child: const Text(
                                        '입력 완료',
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
                              ],
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
                          '만날 장소 (송도)',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                        const SizedBox(height: 10),
                        if (_placesLoading)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: Center(child: CupertinoActivityIndicator()),
                          )
                        else
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: () async {
                              final picked = await PromisePlacePickerSheet.show(
                                context,
                                initialPlaceId: _selectedPlace?.placeId,
                              );
                              if (picked != null && mounted) {
                                setState(() => _selectedPlace = picked);
                              }
                            },
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 16,
                              ),
                              decoration: BoxDecoration(
                                color: _selectedPlace != null
                                    ? _AppColors.primarySoft.withValues(
                                        alpha: _AppColors.promiseFillAlphaLight,
                                      )
                                    : CupertinoColors.white,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: _selectedPlace != null
                                      ? _AppColors.primary
                                      : _AppColors.stone100,
                                ),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      _selectedPlace?.name ?? '장소를 선택하세요',
                                      style: TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontSize: 14,
                                        fontWeight: FontWeight.w600,
                                        color: _selectedPlace != null
                                            ? _AppColors.primary
                                            : _AppColors.textSubtle,
                                      ),
                                    ),
                                  ),
                                  if (_selectedPlace != null) ...[
                                    Text(
                                      PromisePlaceCategory.label(
                                        _selectedPlace!.category,
                                      ),
                                      style: const TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                        color: _AppColors.textSubtle,
                                      ),
                                    ),
                                    const SizedBox(width: 6),
                                  ],
                                  const Icon(
                                    CupertinoIcons.chevron_forward,
                                    size: 18,
                                    color: _AppColors.textSubtle,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        const SizedBox(height: 8),
                        const Text(
                          '칸을 누르면 상세가 펼쳐지고, 지도·이 장소 선택을 할 수 있어요',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            color: _AppColors.textSubtle,
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
                            '${_selectedPlace != null ? '${PromisePlaceCategory.label(_selectedPlace!.category)} · ${_selectedPlace!.name}' : '장소를 선택하세요'}',
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
                          onPressed: () {
                            _dismissKeyboard();
                            Navigator.pop(context);
                          },
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
                            _dismissKeyboard();
                            final hour = int.tryParse(
                              hourController.text.trim(),
                            );
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

                            final p = _selectedPlace;
                            if (p == null) {
                              _showValidationDialog(
                                '장소를 선택해주세요.',
                                title: '장소 선택',
                              );
                              return;
                            }

                            final minAllowedDateTime = DateTime.now().add(
                              const Duration(minutes: 10),
                            );
                            if (selectedDateTime.isBefore(minAllowedDateTime)) {
                              _showValidationDialog(
                                '약속 시간은 현재 시각 기준 10분 이후부터 선택할 수 있어요.',
                              );
                              return;
                            }

                            Navigator.pop(
                              context,
                              _PromiseFormResult(
                                dateTime: selectedDateTime,
                                place: p.name,
                                placeCategory: p.category,
                                placeId: p.placeId,
                                placeAddress: p.address.isNotEmpty
                                    ? p.address
                                    : null,
                                placeLat: p.lat,
                                placeLng: p.lng,
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
              ? _AppColors.primarySoft.withValues(
                  alpha: _AppColors.promiseFillAlpha,
                )
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
