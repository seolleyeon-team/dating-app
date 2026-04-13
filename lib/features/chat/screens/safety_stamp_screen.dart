import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' as material;

import '../services/chat_service.dart';
import '../services/safety_stamp_verification_service.dart';
import '../utils/safety_stamp_availability.dart';
import '../../../router/route_names.dart';

class SafetyStampScreen extends StatefulWidget {
  final String roomId;
  final String promiseId;
  final String currentUserId;
  final String partnerId;
  final String partnerName;
  final String myName;

  const SafetyStampScreen({
    super.key,
    required this.roomId,
    required this.promiseId,
    required this.currentUserId,
    required this.partnerId,
    required this.partnerName,
    required this.myName,
  });

  @override
  State<SafetyStampScreen> createState() => _SafetyStampScreenState();
}

class _SafetyStampScreenState extends State<SafetyStampScreen>
    with TickerProviderStateMixin {
  final ChatService _chatService = ChatService();
  final SafetyStampVerificationService _verificationService =
      SafetyStampVerificationService();
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

  @override
  void initState() {
    super.initState();
    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
    _myStampController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 860),
    );
    _partnerStampController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _successController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _subscribeToSafetyStamp();
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

      if (isInitialSnapshot) {
        if (nextMyStamped) {
          _showHydratedMyStamp = true;
        }
        if (nextPartnerStamped) {
          _showHydratedPartnerStamp = true;
        }
      } else if (nextMyStamped && !_isMyStamped) {
        _showHydratedMyStamp = false;
        _myStampController.forward(from: 0);
      }
      if (!isInitialSnapshot && nextPartnerStamped && !_isPartnerStamped) {
        _showHydratedPartnerStamp = false;
        _partnerStampController.forward(from: 0);
      }
      if (shouldPlaySuccess) {
        _didPlaySuccess = true;
        _successController.forward(from: 0);
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

  Future<void> _handleStampPress() async {
    if (_isMyStamped || _isSubmittingMyStamp) return;

    setState(() {
      _isSubmittingMyStamp = true;
    });

    try {
      final verification = await _verificationService
          .verifyNearbyAndCaptureLocation(
            promiseId: widget.promiseId,
            currentUserId: widget.currentUserId,
            partnerUserId: widget.partnerId,
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

      await _chatService.markSafetyStamp(
        roomId: widget.roomId,
        promiseId: widget.promiseId,
        userId: widget.currentUserId,
        phase: _phase.name,
        verification: verification.toFirestoreMap(
          phase: _phase.name,
          verifierUserId: widget.currentUserId,
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
    final isMatched = _isMyStamped && _isPartnerStamped;
    final isCompleted = _phase == SafetyStampPhase.completed;
    final title = visualPhase == SafetyStampPhase.goodbye ? '헤어짐 확인' : '안심 확인';
    final buttonLabel = isCompleted
        ? '인증 완료'
        : _isMyStamped
        ? '도장 완료'
        : (_isSubmittingMyStamp ? '도장 처리 중...' : '도장 찍기');
    final screenWidth = MediaQuery.sizeOf(context).width;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFFFCFD),
      navigationBar: CupertinoNavigationBar(
        border: Border(),
        middle: Text(
          title,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: Color(0xFF23201E),
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

            return Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
              child: Column(
                children: [
                  Expanded(
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Positioned(
                          top: _lerp(-120, 0, successCurve),
                          left: 8,
                          right: 8,
                          child: Opacity(
                            opacity: _successController.value,
                            child: Transform.translate(
                              offset: Offset(
                                0,
                                _lerp(-24, 0, _successController.value),
                              ),
                              child: _SuccessBanner(phase: visualPhase),
                            ),
                          ),
                        ),
                        Positioned(
                          top: _lerp(
                            70 + _floatingOffset(phase: 0.25),
                            150,
                            successCurve,
                          ),
                          left: _lerp(
                            (screenWidth - 96) / 2 - 24,
                            78,
                            successCurve,
                          ),
                          child: _SeatCircle(
                            label: '상대방 자리',
                            size: _lerp(118, 92, successCurve),
                            isStamped: _isPartnerStamped,
                            showSettledStamp: _showHydratedPartnerStamp,
                            stampProgress: _partnerStampController.value,
                            textOpacity: isMatched ? 0.24 : 0.58,
                          ),
                        ),
                        Positioned(
                          top: _lerp(
                            248 + _floatingOffset(phase: 1.2),
                            150,
                            successCurve,
                          ),
                          left: _lerp(
                            (screenWidth - 196) / 2 - 24,
                            screenWidth - 194,
                            successCurve,
                          ),
                          child: _SeatCircle(
                            label: '내 자리',
                            size: _lerp(188, 92, successCurve),
                            isStamped: _isMyStamped,
                            showSettledStamp: _showHydratedMyStamp,
                            stampProgress: _myStampController.value,
                            textOpacity: _isMyStamped ? 0.24 : 0.72,
                            helperText: _isMyStamped
                                ? null
                                : visualPhase == SafetyStampPhase.goodbye
                                ? '헤어질 때\n도장을 남겨요'
                                : '도장 버튼으로\n만남을 기록해요',
                          ),
                        ),
                      ],
                    ),
                  ),
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
                        backgroundColor: const Color(0xFF23201E),
                        foregroundColor: material.Colors.white,
                        disabledBackgroundColor: const Color(
                          0xFF23201E,
                        ).withValues(alpha: 0.36),
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(18),
                        ),
                      ),
                      child: Text(
                        buttonLabel,
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
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
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
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

  double _floatingOffset({required double phase}) {
    return math.sin((_floatController.value * math.pi * 2) + phase) * 7;
  }
}

class _SeatCircle extends StatelessWidget {
  final String label;
  final double size;
  final bool isStamped;
  final bool showSettledStamp;
  final double stampProgress;
  final double textOpacity;
  final String? helperText;

  const _SeatCircle({
    required this.label,
    required this.size,
    required this.isStamped,
    required this.showSettledStamp,
    required this.stampProgress,
    required this.textOpacity,
    this.helperText,
  });

  @override
  Widget build(BuildContext context) {
    final visualStampProgress = showSettledStamp ? 1.0 : stampProgress;
    final stampDrop = _stampDropOffset(visualStampProgress);
    final stampScale = _stampScale(visualStampProgress);
    final stampRotation = _stampRotation(visualStampProgress);
    final stampOpacity = _stampOpacity(visualStampProgress);
    final stampSquash = _stampSquash(visualStampProgress);
    final bodyOffset = _stampBodyOffset(visualStampProgress);
    final bodyDx = _stampBodyDx(visualStampProgress);
    final bodyScale = _stampBodyScale(visualStampProgress);
    final bodyRotation = _stampBodyRotation(visualStampProgress);
    final bodyOpacity = _stampBodyOpacity(visualStampProgress);
    final bodyTiltX = _stampBodyTiltX(visualStampProgress);
    final bodyTiltY = _stampBodyTiltY(visualStampProgress);
    final bodyShadowOpacity = _stampBodyShadowOpacity(visualStampProgress);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          CustomPaint(
            size: Size.square(size),
            painter: _DashedCirclePainter(),
            child: Container(
              width: size,
              height: size,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color(0xFFFFFEFE),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    label,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: size * 0.13,
                      height: 1.2,
                      fontWeight: FontWeight.w700,
                      color: const Color(
                        0xFF23201E,
                      ).withValues(alpha: textOpacity),
                    ),
                  ),
                  if (helperText != null) ...[
                    SizedBox(height: size * 0.06),
                    Text(
                      helperText!,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: size * 0.09,
                        height: 1.2,
                        fontWeight: FontWeight.w600,
                        color: const Color(0xFFB1ABA6),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          if (isStamped && bodyOpacity > 0)
            Transform.translate(
              offset: Offset(bodyDx, bodyOffset),
              child: Transform(
                alignment: Alignment.center,
                transform: Matrix4.identity()
                  ..setEntry(3, 2, 0.0014)
                  ..rotateX(bodyTiltX)
                  ..rotateY(bodyTiltY)
                  ..rotateZ(bodyRotation),
                child: Transform.scale(
                  scale: bodyScale,
                  child: Opacity(
                    opacity: bodyOpacity,
                    child: _StampBody(
                      size: size * 0.98,
                      shadowOpacity: bodyShadowOpacity,
                    ),
                  ),
                ),
              ),
            ),
          if (isStamped)
            Transform.translate(
              offset: Offset(0, stampDrop),
              child: Transform.rotate(
                angle: stampRotation,
                child: Transform.scale(
                  scaleX: stampScale,
                  scaleY: stampScale * stampSquash,
                  child: Opacity(
                    opacity: stampOpacity,
                    child: _StampSeal(size: size * 0.7),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  double _stampDropOffset(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress <= 0.58) {
      return size * 0.06;
    }
    if (safeProgress < 0.8) {
      final reveal = Curves.easeOutCubic.transform(
        _clampUnit((safeProgress - 0.58) / 0.22),
      );
      return ui.lerpDouble(size * 0.06, 0, reveal) ?? 0;
    }
    final settle = Curves.easeOutBack.transform(
      _clampUnit((safeProgress - 0.8) / 0.2),
    );
    return ui.lerpDouble(0, 2, settle) ?? 2;
  }

  double _stampScale(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress <= 0.58) return 0.88;
    if (safeProgress < 0.82) {
      return ui.lerpDouble(
            0.82,
            1.0,
            Curves.easeOutExpo.transform(
              _clampUnit((safeProgress - 0.58) / 0.24),
            ),
          ) ??
          1;
    }
    return ui.lerpDouble(
          1.0,
          1.0,
          _clampUnit(
            Curves.easeOutBack.transform(
              _clampUnit((safeProgress - 0.82) / 0.18),
            ),
          ),
        ) ??
        1;
  }

  double _stampSquash(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress <= 0.58) return 1.05;
    if (safeProgress < 0.76) {
      return ui.lerpDouble(
            1.08,
            0.94,
            Curves.easeOut.transform(_clampUnit((safeProgress - 0.58) / 0.18)),
          ) ??
          0.94;
    }
    return ui.lerpDouble(
          0.94,
          1.0,
          Curves.easeOutBack.transform(
            _clampUnit((safeProgress - 0.76) / 0.24),
          ),
        ) ??
        1.0;
  }

  double _stampRotation(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress <= 0.58) return -0.1;
    return ui.lerpDouble(
          -0.12,
          -0.02,
          Curves.easeOutCubic.transform(
            _clampUnit((safeProgress - 0.58) / 0.42),
          ),
        ) ??
        -0.02;
  }

  double _stampOpacity(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress <= 0.58) return 0;
    if (safeProgress < 0.72) {
      return Curves.easeOut.transform(_clampUnit((safeProgress - 0.58) / 0.14));
    }
    return 1;
  }

  double _stampBodyOffset(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.6) {
      return ui.lerpDouble(
            -size * 1.26,
            -size * 0.03,
            Curves.easeInCubic.transform(safeProgress / 0.6),
          ) ??
          (-size * 1.26);
    }
    return ui.lerpDouble(
          -size * 0.02,
          -size * 0.92,
          Curves.easeInOutCubic.transform(
            _clampUnit((safeProgress - 0.6) / 0.4),
          ),
        ) ??
        (-size * 0.92);
  }

  double _stampBodyScale(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.55) {
      return ui.lerpDouble(
            1.08,
            0.96,
            Curves.easeOutCubic.transform(safeProgress / 0.55),
          ) ??
          0.96;
    }
    return ui.lerpDouble(
          0.96,
          1.02,
          Curves.easeIn.transform(_clampUnit((safeProgress - 0.55) / 0.45)),
        ) ??
        1.02;
  }

  double _stampBodyRotation(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.58) {
      return ui.lerpDouble(
            -0.38,
            -0.1,
            Curves.easeOutCubic.transform(safeProgress / 0.58),
          ) ??
          -0.1;
    }
    return ui.lerpDouble(
          -0.1,
          -0.04,
          Curves.easeOut.transform(_clampUnit((safeProgress - 0.58) / 0.42)),
        ) ??
        -0.04;
  }

  double _stampBodyOpacity(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.08) return safeProgress / 0.08;
    if (safeProgress < 0.76) return 1;
    return ui.lerpDouble(
          1,
          0,
          Curves.easeIn.transform(_clampUnit((safeProgress - 0.76) / 0.24)),
        ) ??
        0;
  }

  double _stampBodyDx(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.6) {
      return ui.lerpDouble(
            size * 0.34,
            size * 0.06,
            Curves.easeOutCubic.transform(safeProgress / 0.6),
          ) ??
          (size * 0.06);
    }
    return ui.lerpDouble(
          size * 0.06,
          size * 0.16,
          Curves.easeInOut.transform(_clampUnit((safeProgress - 0.6) / 0.4)),
        ) ??
        (size * 0.16);
  }

  double _stampBodyTiltX(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.6) {
      return ui.lerpDouble(
            0.98,
            0.28,
            Curves.easeOutCubic.transform(safeProgress / 0.6),
          ) ??
          0.28;
    }
    return ui.lerpDouble(
          0.28,
          0.72,
          Curves.easeIn.transform(_clampUnit((safeProgress - 0.6) / 0.4)),
        ) ??
        0.72;
  }

  double _stampBodyTiltY(double progress) {
    final safeProgress = _clampUnit(progress);
    return ui.lerpDouble(
          -0.26,
          -0.08,
          Curves.easeOut.transform(safeProgress),
        ) ??
        -0.08;
  }

  double _stampBodyShadowOpacity(double progress) {
    final safeProgress = _clampUnit(progress);
    if (safeProgress < 0.58) {
      return ui.lerpDouble(
            0.08,
            0.2,
            Curves.easeIn.transform(safeProgress / 0.58),
          ) ??
          0.2;
    }
    return ui.lerpDouble(
          0.2,
          0.1,
          Curves.easeOut.transform(_clampUnit((safeProgress - 0.58) / 0.42)),
        ) ??
        0.1;
  }
}

class _StampSeal extends StatelessWidget {
  final double size;

  const _StampSeal({required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: const Color(0xFFDF5A59).withValues(alpha: 0.08),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: size * 0.92,
            height: size * 0.92,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: const Color(0xFFDF5A59).withValues(alpha: 0.82),
                width: size * 0.038,
              ),
            ),
          ),
          Container(
            width: size * 0.72,
            height: size * 0.72,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: const Color(0xFFDF5A59).withValues(alpha: 0.28),
                width: size * 0.02,
              ),
            ),
          ),
          Container(
            width: size * 0.22,
            height: size * 0.22,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFDF5A59).withValues(alpha: 0.12),
            ),
          ),
          Transform.rotate(
            angle: -0.18,
            child: Text(
              'M',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: size * 0.28,
                fontWeight: FontWeight.w900,
                letterSpacing: -2,
                color: const Color(0xFFDF5A59).withValues(alpha: 0.82),
              ),
            ),
          ),
          Positioned(
            top: size * 0.19,
            child: Text(
              'MEET VERIFIED',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: size * 0.055,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
                color: const Color(0xFFDF5A59).withValues(alpha: 0.78),
              ),
            ),
          ),
          Positioned(
            bottom: size * 0.2,
            child: Text(
              'CONFIRMED',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: size * 0.06,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.4,
                color: const Color(0xFFDF5A59).withValues(alpha: 0.65),
              ),
            ),
          ),
          Positioned(
            left: size * 0.24,
            child: Transform.rotate(
              angle: -0.72,
              child: Container(
                width: size * 0.014,
                height: size * 0.17,
                color: const Color(0xFFDF5A59).withValues(alpha: 0.38),
              ),
            ),
          ),
          Positioned(
            right: size * 0.24,
            child: Transform.rotate(
              angle: 0.72,
              child: Container(
                width: size * 0.014,
                height: size * 0.17,
                color: const Color(0xFFDF5A59).withValues(alpha: 0.38),
              ),
            ),
          ),
          Positioned(
            left: size * 0.14,
            top: size * 0.18,
            child: _InkSpot(size: size * 0.07),
          ),
          Positioned(
            right: size * 0.16,
            bottom: size * 0.18,
            child: _InkSpot(size: size * 0.045),
          ),
        ],
      ),
    );
  }
}

class _StampBody extends StatelessWidget {
  final double size;
  final double shadowOpacity;

  const _StampBody({required this.size, required this.shadowOpacity});

  @override
  Widget build(BuildContext context) {
    final knobSize = size * 0.34;
    final neckWidth = size * 0.16;
    final neckHeight = size * 0.2;
    final plateWidth = size * 0.76;
    final plateHeight = size * 0.34;

    return SizedBox(
      width: size * 0.9,
      height: size,
      child: Stack(
        alignment: Alignment.topCenter,
        clipBehavior: Clip.none,
        children: [
          Positioned(
            top: size * 0.69,
            child: Container(
              width: plateWidth * 0.86,
              height: size * 0.09,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                color: material.Colors.black.withValues(alpha: shadowOpacity),
                boxShadow: [
                  BoxShadow(
                    color: material.Colors.black.withValues(
                      alpha: shadowOpacity * 0.7,
                    ),
                    blurRadius: 18,
                    spreadRadius: 1,
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            top: size * 0.08,
            child: Container(
              width: knobSize,
              height: knobSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFFFFFFFF),
                    Color(0xFFF3F3F1),
                    Color(0xFFD6D8D7),
                  ],
                ),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x18000000),
                    blurRadius: 16,
                    offset: Offset(0, 8),
                  ),
                ],
              ),
              child: Stack(
                children: [
                  Positioned(
                    left: knobSize * 0.16,
                    top: knobSize * 0.12,
                    child: _HandleHighlight(
                      width: knobSize * 0.14,
                      height: knobSize * 0.2,
                    ),
                  ),
                  Positioned(
                    left: knobSize * 0.34,
                    top: knobSize * 0.08,
                    child: _HandleHighlight(
                      width: knobSize * 0.1,
                      height: knobSize * 0.13,
                    ),
                  ),
                  Positioned(
                    right: knobSize * 0.18,
                    top: knobSize * 0.18,
                    child: Container(
                      width: knobSize * 0.1,
                      height: knobSize * 0.1,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Color(0x55FFFFFF),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            top: size * 0.3,
            child: Container(
              width: neckWidth,
              height: neckHeight,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(neckWidth),
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0xFFF9F9F7),
                    Color(0xFFE8E8E5),
                    Color(0xFFD6D7D5),
                  ],
                ),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x12000000),
                    blurRadius: 8,
                    offset: Offset(0, 4),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            top: size * 0.46,
            child: Container(
              width: neckWidth * 1.3,
              height: size * 0.032,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                gradient: const LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0xFFF0F0EE), Color(0xFFD8D9D7)],
                ),
              ),
            ),
          ),
          Positioned(
            top: size * 0.39,
            child: Container(
              width: neckWidth * 1.35,
              height: size * 0.08,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0xFFF5F5F3), Color(0xFFD7D8D5)],
                ),
              ),
            ),
          ),
          Positioned(
            top: size * 0.46,
            child: Container(
              width: plateWidth,
              height: plateHeight,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(size * 0.08),
                gradient: const LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0xFFFFFFFF),
                    Color(0xFFF1F2F0),
                    Color(0xFFD8DAD8),
                  ],
                ),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x16000000),
                    blurRadius: 16,
                    offset: Offset(0, 9),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            top: size * 0.48,
            child: Container(
              width: plateWidth * 0.9,
              height: plateHeight * 0.18,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                gradient: const LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0x66FFFFFF), Color(0x00FFFFFF)],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HandleHighlight extends StatelessWidget {
  final double width;
  final double height;

  const _HandleHighlight({required this.width, required this.height});

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: -0.42,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(width),
          color: const Color(0x78FFFFFF),
        ),
      ),
    );
  }
}

class _InkSpot extends StatelessWidget {
  final double size;

  const _InkSpot({required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: const Color(0xFFD84D4D).withValues(alpha: 0.45),
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
        color: const Color(0xFFF8F4F1),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFEAE2DD)),
      ),
      child: Column(
        children: [
          _StatusRow(
            title: phase == SafetyStampPhase.goodbye ? '내 헤어짐 도장' : '내 만남 도장',
            value: isMyStamped ? '완료' : '대기 중',
            isDone: isMyStamped,
          ),
          const SizedBox(height: 10),
          _StatusRow(
            title: phase == SafetyStampPhase.goodbye
                ? '상대방 헤어짐 도장'
                : '상대방 만남 도장',
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
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: Color(0xFF403A36),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: isDone ? const Color(0xFFE9F7EC) : const Color(0xFFF1ECE8),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            value,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: isDone ? const Color(0xFF2A8A50) : const Color(0xFF8E827A),
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
        ? '둘 다 만남 도장을 남겼어요. 헤어질 때 한 번 더 도장을 남겨주세요.'
        : '둘 다 헤어짐 도장을 남겨서 약속이 잘 마무리되었어요.';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 24),
      decoration: BoxDecoration(
        color: material.Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE2DED9)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 24,
            offset: Offset(0, 10),
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
              fontFamily: 'Pretendard',
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: Color(0xFF4B4A48),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(0xFF8A847D),
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

class _DashedCirclePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFB8B1AB)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8;

    final radius = size.width / 2 - 1.5;
    const dashCount = 28;
    const dashSweep = 0.14;
    const gapSweep = 0.085;
    final rect = Rect.fromCircle(
      center: Offset(size.width / 2, size.height / 2),
      radius: radius,
    );

    double start = -math.pi / 2;
    for (int i = 0; i < dashCount; i++) {
      canvas.drawArc(rect, start, dashSweep, false, paint);
      start += dashSweep + gapSweep;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
