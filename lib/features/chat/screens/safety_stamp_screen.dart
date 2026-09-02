import 'dart:async';
import 'dart:ui' as ui;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' as material;

import '../../profile/models/safety_stamp_log_entry.dart';
import '../../profile/services/safety_stamp_log_cache_service.dart';
import '../../../services/user_service.dart';
import '../services/chat_service.dart';
import '../services/safety_stamp_verification_service.dart';
import '../utils/safety_stamp_availability.dart';
import '../widgets/safety_stamp_motion/safety_stamp_slot_motion.dart';
import '../../../router/route_names.dart';

class SafetyStampScreen extends StatefulWidget {
  final String roomId;
  final String promiseId;
  final String currentUserId;
  final String partnerId;
  final String partnerName;
  final String myName;
  final bool motionPreviewMode;
  final bool motion3dEnabled;

  const SafetyStampScreen({
    super.key,
    required this.roomId,
    required this.promiseId,
    required this.currentUserId,
    required this.partnerId,
    required this.partnerName,
    required this.myName,
    this.motionPreviewMode = false,
    this.motion3dEnabled = true,
  });

  @override
  State<SafetyStampScreen> createState() => _SafetyStampScreenState();
}

class _SafetyStampScreenState extends State<SafetyStampScreen>
    with TickerProviderStateMixin {
  late final ChatService _chatService;
  late final SafetyStampLogCacheService _logCacheService;
  late final UserService _userService;
  late final SafetyStampVerificationService _verificationService;
  late final AnimationController _floatController;
  late final AnimationController _myStampController;
  late final AnimationController _partnerStampController;
  late final AnimationController _successController;
  StreamSubscription<DocumentSnapshot<Map<String, dynamic>>>? _roomSubscription;

  bool _isMyStamped = false;
  bool _isPartnerStamped = false;
  bool _isSubmittingMyStamp = false;
  bool _didPlaySuccess = false;
  bool _holdMeetupSuccessView = false;
  bool _hasReceivedInitialSnapshot = false;
  bool _showHydratedMyStamp = false;
  bool _showHydratedPartnerStamp = false;
  SafetyStampPhase _phase = SafetyStampPhase.meetup;
  String _currentPlaceName = '위치 정보 없음';
  bool _shouldUseGpsFallbackForPartner = false;
  bool _isCancellingExpiredPromise = false;

  @override
  void initState() {
    super.initState();
    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
    _myStampController = AnimationController(
      vsync: this,
      duration: SafetyStampMotionTiming.total,
    );
    _partnerStampController = AnimationController(
      vsync: this,
      duration: SafetyStampMotionTiming.total,
    );
    _successController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    if (widget.motionPreviewMode) {
      _hasReceivedInitialSnapshot = true;
      _isPartnerStamped = true;
      _showHydratedPartnerStamp = true;
      return;
    }
    _chatService = ChatService();
    _logCacheService = SafetyStampLogCacheService();
    _userService = UserService();
    _verificationService = SafetyStampVerificationService();
    _loadPartnerPlatform();
    _subscribeToSafetyStamp();
  }

  Future<void> _loadPartnerPlatform() async {
    if (widget.partnerId.isEmpty) return;

    final partnerProfile = await _userService.getUserProfile(widget.partnerId);
    final partnerPlatform =
        partnerProfile?['lastActivePlatform']?.toString().toLowerCase() ?? '';

    if (!mounted) return;
    setState(() {
      _shouldUseGpsFallbackForPartner = partnerPlatform == 'web';
    });
  }

  @override
  void dispose() {
    _roomSubscription?.cancel();
    _floatController.dispose();
    _myStampController.dispose();
    _partnerStampController.dispose();
    _successController.dispose();
    super.dispose();
  }

  void _subscribeToSafetyStamp() {
    if (widget.roomId.isEmpty || widget.promiseId.isEmpty) return;

    _roomSubscription = _chatService.roomStream(widget.roomId).listen((
      snapshot,
    ) {
      final roomData = snapshot.data();
      final activePromiseRaw = roomData?['activePromise'];
      final activePromise = activePromiseRaw is Map
          ? Map<String, dynamic>.from(activePromiseRaw)
          : null;
      final activePromiseId = activePromise?['promiseId']?.toString() ?? '';
      if (activePromise == null || activePromiseId != widget.promiseId) {
        return;
      }
      _cancelExpiredPromiseIfNeeded(activePromise);
      _currentPlaceName =
          activePromise['place']?.toString().trim().isNotEmpty == true
          ? activePromise['place'].toString().trim()
          : '위치 정보 없음';

      final nextPhase = deriveSafetyStampPhase(activePromise);
      final safetyStampRaw = activePromise['safetyStamp'];
      final safetyStamp = safetyStampRaw is Map
          ? Map<String, dynamic>.from(safetyStampRaw)
          : const <String, dynamic>{};
      final meetupStampedUserIds =
          (safetyStamp['meetupStampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      final legacyStampedUserIds =
          (safetyStamp['stampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      final effectiveMeetupStampedUserIds = meetupStampedUserIds.isNotEmpty
          ? meetupStampedUserIds
          : legacyStampedUserIds;
      final goodbyeStampedUserIds =
          (safetyStamp['goodbyeStampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      final isInitialSnapshot = !_hasReceivedInitialSnapshot;
      final isMeetupCompletedNow =
          !isInitialSnapshot &&
          nextPhase == SafetyStampPhase.goodbye &&
          _phase == SafetyStampPhase.meetup &&
          effectiveMeetupStampedUserIds.contains(widget.currentUserId) &&
          effectiveMeetupStampedUserIds.contains(widget.partnerId);

      if (isMeetupCompletedNow) {
        _holdMeetupSuccessView = true;
      }

      final displayPhase = _holdMeetupSuccessView
          ? SafetyStampPhase.meetup
          : nextPhase;

      final activeStampedUserIds =
          displayPhase == SafetyStampPhase.goodbye ||
              displayPhase == SafetyStampPhase.completed
          ? goodbyeStampedUserIds
          : effectiveMeetupStampedUserIds;

      final nextMyStamped = activeStampedUserIds.contains(widget.currentUserId);
      final nextPartnerStamped = activeStampedUserIds.contains(
        widget.partnerId,
      );
      final shouldPlaySuccess =
          nextMyStamped &&
          nextPartnerStamped &&
          (!_didPlaySuccess || displayPhase != _phase);
      final newStampAnimations = <Future<void>>[];

      if (isInitialSnapshot) {
        if (nextMyStamped) {
          _showHydratedMyStamp = true;
        }
        if (nextPartnerStamped) {
          _showHydratedPartnerStamp = true;
        }
      } else if (nextMyStamped && !_isMyStamped) {
        _showHydratedMyStamp = false;
        newStampAnimations.add(_myStampController.forward(from: 0).orCancel);
      }
      if (!isInitialSnapshot && nextPartnerStamped && !_isPartnerStamped) {
        _showHydratedPartnerStamp = false;
        newStampAnimations.add(
          _partnerStampController.forward(from: 0).orCancel,
        );
      }
      if (shouldPlaySuccess) {
        _didPlaySuccess = true;
        if (newStampAnimations.isEmpty) {
          _successController.forward(from: 0);
        } else {
          unawaited(
            (() async {
              try {
                await Future.wait(newStampAnimations);
              } catch (_) {
                return;
              }
              if (mounted) _successController.forward(from: 0);
            })(),
          );
        }
      }

      if (displayPhase != _phase && !(nextMyStamped && nextPartnerStamped)) {
        _didPlaySuccess = false;
        _myStampController.reset();
        _partnerStampController.reset();
        _successController.reset();
      }

      if (!mounted) return;
      setState(() {
        _hasReceivedInitialSnapshot = true;
        _phase = nextPhase;
        _isMyStamped = nextMyStamped;
        _isPartnerStamped = nextPartnerStamped;
        _isSubmittingMyStamp = false;
        if (!nextMyStamped) {
          _showHydratedMyStamp = false;
        }
        if (!nextPartnerStamped) {
          _showHydratedPartnerStamp = false;
        }
      });
    });
  }

  Future<void> _cancelExpiredPromiseIfNeeded(
    Map<String, dynamic> activePromise,
  ) async {
    if (_isCancellingExpiredPromise) return;
    if (!isMeetupSafetyStampExpired(activePromise)) return;

    _isCancellingExpiredPromise = true;
    try {
      await _chatService.cancelExpiredIncompleteSafetyStamp(
        roomId: widget.roomId,
        promiseId: widget.promiseId,
      );
    } finally {
      _isCancellingExpiredPromise = false;
    }
  }

  Future<void> _handleStampPress() async {
    if (_isMyStamped || _isSubmittingMyStamp) return;

    setState(() {
      _isSubmittingMyStamp = true;
    });

    if (widget.motionPreviewMode) {
      await Future<void>.delayed(const Duration(milliseconds: 180));
      if (!mounted) return;
      setState(() {
        _isSubmittingMyStamp = false;
        _isMyStamped = true;
        _showHydratedMyStamp = false;
      });
      try {
        await _myStampController.forward(from: 0).orCancel;
      } catch (_) {
        return;
      }
      if (!mounted) return;
      _didPlaySuccess = true;
      _successController.forward(from: 0);
      return;
    }

    try {
      final verification = await _verificationService
          .verifyNearbyAndCaptureLocation(
            promiseId: widget.promiseId,
            currentUserId: widget.currentUserId,
            partnerUserId: widget.partnerId,
            preferGpsOnly: _shouldUseGpsFallbackForPartner,
          );

      if (!verification.isSuccess) {
        if (!mounted) return;
        setState(() {
          _isSubmittingMyStamp = false;
        });
        await _showWarningDialog(
          title: '안전도장을 찍을 수 없어요',
          message: verification.message,
        );
        return;
      }

      // uid 는 서버가 auth 컨텍스트에서 정한다 (클라이언트가 지정하지 않는다).
      await _chatService.markSafetyStamp(
        roomId: widget.roomId,
        promiseId: widget.promiseId,
        phase: _phase.name,
        verification: verification.toFirestoreMap(
          phase: _phase.name,
          verifierUserId: widget.currentUserId,
        ),
      );
      await _logCacheService.saveLog(
        widget.currentUserId,
        SafetyStampLogEntry(
          logId: '${widget.promiseId}_${_phase.name}_${widget.currentUserId}',
          promiseId: widget.promiseId,
          roomId: widget.roomId,
          partnerId: widget.partnerId,
          partnerName: widget.partnerName,
          phase: _phase.name,
          placeName: _currentPlaceName,
          stampedAt: verification.location?.capturedAt ?? DateTime.now(),
          latitude: verification.location?.latitude,
          longitude: verification.location?.longitude,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isSubmittingMyStamp = false;
      });
      showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('도장을 찍지 못했어요'),
          content: const Text('잠시 후 다시 시도해주세요.'),
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

  Future<void> _showWarningDialog({
    required String title,
    required String message,
  }) {
    return showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  void _goHome() {
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    final visualPhase = _holdMeetupSuccessView
        ? SafetyStampPhase.meetup
        : _phase;
    final isCompleted = _phase == SafetyStampPhase.completed;
    final title = visualPhase == SafetyStampPhase.goodbye ? '헤어짐 확인' : '안심 확인';
    final buttonLabel = isCompleted
        ? '인증 완료'
        : _isMyStamped
        ? '도장 완료'
        : (_isSubmittingMyStamp ? '도장 처리 중...' : '도장 찍기');
    final screenWidth = MediaQuery.sizeOf(context).width;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFF8F8F8),
      navigationBar: CupertinoNavigationBar(
        backgroundColor: const Color(0xFFF8F8F8),
        border: const Border(),
        middle: Text(
          title,
          style: const TextStyle(
            fontFamily: 'NanumSquareRound',
            fontWeight: FontWeight.w700,
            color: Color(0xFF222222),
          ),
        ),
      ),
      child: SafeArea(
        child: AnimatedBuilder(
          animation: Listenable.merge([
            _floatController,
            _myStampController,
            _partnerStampController,
            _successController,
          ]),
          builder: (context, _) {
            final successCurve = Curves.easeOutBack.transform(
              _successController.value,
            );

            final cardWidth = screenWidth - 32;
            const slotCardHeight = 186.0;

            // 애니메이션 중에는 상태카드/버튼 fade out + 클릭 차단
            final myAnim = _myStampController.value;
            final partnerAnim = _partnerStampController.value;
            final isAnyAnimating =
                (myAnim > 0 && myAnim < 1) ||
                (partnerAnim > 0 && partnerAnim < 1);
            final controlsOpacity = isAnyAnimating ? 0.0 : 1.0;
            final trimmedPartnerName = widget.partnerName.trim();
            final partnerSlotLabel = trimmedPartnerName.isEmpty
                ? '상대방 칸'
                : trimmedPartnerName.endsWith('님')
                ? '$trimmedPartnerName 칸'
                : '$trimmedPartnerName님 칸';

            return Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
              child: Column(
                children: [
                  Expanded(
                    child: Stack(
                      clipBehavior: Clip.none,
                      alignment: Alignment.center,
                      children: [
                        Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              _StickerSlotCard(
                                label: partnerSlotLabel,
                                cardWidth: cardWidth,
                                cardHeight: slotCardHeight,
                                stickerSize: 210,
                                isStamped: _isPartnerStamped,
                                showSettledStamp: _showHydratedPartnerStamp,
                                stampProgress: partnerAnim,
                                settledRotationDeg: 5.0,
                                emphasis: false,
                                enable3d: widget.motion3dEnabled,
                              ),
                              const SizedBox(height: 14),
                              _StickerSlotCard(
                                label: '내 칸',
                                cardWidth: cardWidth,
                                cardHeight: slotCardHeight,
                                stickerSize: 260,
                                isStamped: _isMyStamped,
                                showSettledStamp: _showHydratedMyStamp,
                                stampProgress: myAnim,
                                settledRotationDeg: -3.0,
                                emphasis: true,
                                enable3d: widget.motion3dEnabled,
                                helperText: _isMyStamped
                                    ? null
                                    : visualPhase == SafetyStampPhase.goodbye
                                    ? '헤어질 때 벚꽃 스티커를 남겨요'
                                    : '만남 후 벚꽃 스티커를 남겨요',
                              ),
                            ],
                          ),
                        ),
                        if (_successController.value > 0)
                          Positioned(
                            top: _lerp(-80, 8, successCurve),
                            left: 0,
                            right: 0,
                            child: Opacity(
                              opacity: _clampUnit(_successController.value),
                              child: _SuccessBanner(phase: visualPhase),
                            ),
                          ),
                      ],
                    ),
                  ),
                  IgnorePointer(
                    ignoring: isAnyAnimating,
                    child: AnimatedOpacity(
                      duration: const Duration(milliseconds: 180),
                      opacity: controlsOpacity,
                      child: Column(
                        children: [
                          _StatusCard(
                            phase: visualPhase,
                            isMyStamped: _isMyStamped,
                            isPartnerStamped: _isPartnerStamped,
                          ),
                          const SizedBox(height: 16),
                          SizedBox(
                            width: double.infinity,
                            height: 56,
                            child: material.ElevatedButton(
                              onPressed:
                                  (_holdMeetupSuccessView ||
                                      isCompleted ||
                                      _isMyStamped ||
                                      _isSubmittingMyStamp)
                                  ? null
                                  : _handleStampPress,
                              style: material.ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF222222),
                                foregroundColor: material.Colors.white,
                                disabledBackgroundColor: const Color(
                                  0xFF222222,
                                ).withValues(alpha: 0.32),
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(18),
                                ),
                              ),
                              child: Text(
                                buttonLabel,
                                style: const TextStyle(
                                  fontFamily: 'NanumSquareRound',
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            width: double.infinity,
                            height: 56,
                            child: material.ElevatedButton(
                              onPressed: _goHome,
                              style: material.ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFFF07F9D),
                                foregroundColor: material.Colors.white,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                              ),
                              child: const Text(
                                '홈으로 돌아가기',
                                style: TextStyle(
                                  fontFamily: 'NanumSquareRound',
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 벚꽃 스티커 보드 — 종이 카드 위에 cherrysticker.png가 "착착착" 붙는 UI
// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// 스케치북 종이 카드 — 배경: sketchbook.png / 스티커는 외부 Stack에 올라가
// clipBehavior: Clip.none 이므로 스티커가 카드 밖에 있어도 절대 잘리지 않음
// ─────────────────────────────────────────────────────────────────────────────
class _StickerSlotCard extends StatelessWidget {
  final String label;
  final double cardWidth;
  final double cardHeight;
  final double stickerSize;
  final bool isStamped;
  final bool showSettledStamp;
  final double stampProgress;
  final double settledRotationDeg;
  final bool emphasis;
  final bool enable3d;
  final String? helperText;

  const _StickerSlotCard({
    required this.label,
    required this.cardWidth,
    required this.cardHeight,
    required this.stickerSize,
    required this.isStamped,
    required this.showSettledStamp,
    required this.stampProgress,
    required this.settledRotationDeg,
    required this.emphasis,
    required this.enable3d,
    this.helperText,
  });

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final forceSettled = showSettledStamp || (reduceMotion && isStamped);
    final progress = forceSettled ? 1.0 : stampProgress;

    // SizedBox로 레이아웃 크기를 카드 크기에 고정하면서도,
    // clipBehavior: Clip.none으로 스티커가 카드 밖을 자유롭게 이동 가능
    return SizedBox(
      width: cardWidth,
      height: cardHeight,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          // ── 카드 본체: sketchbook.png 배경 (ClipRRect는 카드 배경에만 적용) ──
          ClipRRect(
            borderRadius: BorderRadius.circular(17),
            child: Container(
              width: cardWidth,
              height: cardHeight,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(17),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x0D000000),
                    blurRadius: 12,
                    offset: Offset(0, 5),
                  ),
                ],
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  // sketchbook.png 질감 배경
                  Image.asset('sketchbook.png', fit: BoxFit.cover),
                  // 아주 연한 화이트 오버레이 — 과한 빈티지 억제
                  Container(color: const Color(0x18FFFFFF)),
                  // 라벨
                  Positioned(
                    top: 16,
                    left: 17,
                    child: Text(
                      label,
                      style: TextStyle(
                        fontFamily: 'NanumSquareRound',
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: emphasis
                            ? const Color(0xFF7A736C)
                            : const Color(0xFF8E8880),
                        letterSpacing: -0.2,
                      ),
                    ),
                  ),
                  // 미완료 안내 텍스트
                  if (!isStamped)
                    Center(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(28, 12, 28, 0),
                        child: Text(
                          helperText ?? '아직 확인 전이에요',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontFamily: 'NanumSquareRound',
                            fontSize: 13,
                            fontWeight: FontWeight.w400,
                            color: Color(0xFFB0A9A3),
                            height: 1.4,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),

          // 각 칸은 독립된 타임라인과 3D 모델을 사용한다. 그래서 내 도장과
          // 상대 도장이 서로 다른 시점에 도착해도 원래의 2분할 상태를 지킨다.
          Positioned.fill(
            child: SafetyStampSlotMotion(
              timeline: progress,
              isVisible: isStamped,
              forceSettled: forceSettled,
              stickerSize: stickerSize,
              settledRotationDeg: settledRotationDeg,
              enable3d: enable3d,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  final SafetyStampPhase phase;
  final bool isMyStamped;
  final bool isPartnerStamped;

  const _StatusCard({
    required this.phase,
    required this.isMyStamped,
    required this.isPartnerStamped,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: material.Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFEADDE1)),
      ),
      child: Column(
        children: [
          _StatusRow(
            title: phase == SafetyStampPhase.goodbye ? '내 헤어짐 확인' : '내 안전 확인',
            value: isMyStamped ? '완료' : '대기 중',
            isDone: isMyStamped,
          ),
          const SizedBox(height: 10),
          _StatusRow(
            title: phase == SafetyStampPhase.goodbye
                ? '상대방 헤어짐 확인'
                : '상대방 안전 확인',
            value: isPartnerStamped ? '완료' : '아직 확인 전',
            isDone: isPartnerStamped,
          ),
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final String title;
  final String value;
  final bool isDone;

  const _StatusRow({
    required this.title,
    required this.value,
    required this.isDone,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontFamily: 'NanumSquareRound',
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: Color(0xFF333333),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: isDone ? const Color(0xFFFCEFF3) : const Color(0xFFF3F3F3),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            value,
            style: TextStyle(
              fontFamily: 'NanumSquareRound',
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: isDone ? const Color(0xFFD95C7D) : const Color(0xFF8A8A8A),
            ),
          ),
        ),
      ],
    );
  }
}

class _SuccessBanner extends StatelessWidget {
  final SafetyStampPhase phase;

  const _SuccessBanner({required this.phase});

  @override
  Widget build(BuildContext context) {
    final isMeetupSuccess = phase == SafetyStampPhase.meetup;
    final title = isMeetupSuccess ? '만남이 성사되었어요!' : '약속이 정상적으로 완료되었어요!';
    final subtitle = isMeetupSuccess
        ? '둘 다 벚꽃 스티커를 남겼어요. 헤어질 때 한 번 더 스티커를 남겨주세요.'
        : '둘 다 헤어짐 확인을 남겨서 약속이 잘 마무리되었어요.';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
      decoration: BoxDecoration(
        color: material.Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFEADDE1)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x12000000),
            blurRadius: 20,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'NanumSquareRound',
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: Color(0xFF222222),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'NanumSquareRound',
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(0xFF666666),
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }
}

double _lerp(double begin, double end, double t) {
  final clampedT = _clampUnit(t);
  return ui.lerpDouble(begin, end, clampedT) ?? end;
}

double _clampUnit(double value) {
  if (value.isNaN) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}
