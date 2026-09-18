import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../router/route_names.dart';
import '../../../services/avatar_generation_client.dart';
import '../../../services/avatar_source_photo_service.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../services/avatar_generation_session_controller.dart';
import '../widgets/avatar_candidate_selection_dialog.dart';
import '../widgets/avatar_generating_overlay.dart';
import '../widgets/avatar_generation_messages.dart';
import '../widgets/avatar_generation_models.dart';

const String avatarSelectStatusUnavailableMessage =
    '아바타 생성 상태를 확인하지 못했어요. 잠시 후 다시 확인해주세요.';
const String avatarSelectNoJobMessage =
    '아바타 생성이 시작되지 않았어요. 사진을 등록하고 다시 만들어주세요.';
const String avatarSelectApprovalErrorMessage = '아바타 저장에 실패했어요. 다시 한 번 선택해주세요.';
const String avatarSelectCheckAgainLabel = '다시 확인';
const String avatarSelectGoToPhotosLabel = '사진 등록하러 가기';
const String avatarSelectRetryLabel = '다시 시도';

class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color progressBg = Color(0xFFE6DBDF);
}

/// 온보딩 마지막 단계: 아바타 선택.
///
/// 세션 컨트롤러 상태로 분기한다.
/// - previewReady: 후보를 불러와 [AvatarCandidateSelectionDialog] 를 화면 본문으로
///   보여주고, 승인 → `completeOnboarding` → 튜토리얼.
/// - generating: [AvatarGeneratingOverlay] 대기 화면. 컨트롤러가 previewReady 로
///   바뀌면 자동으로 선택 UI 로 전환.
/// - attention: resume policy 메시지 + 서버가 허용할 때만 재시도 /
///   "사진을 바꾸고 다시 만들기"(replace 후 사진 화면). reconciliation 은 안내만.
/// - approved: 곧바로 온보딩 완료.
/// - idle(작업 없음) / unavailable(상태 조회 실패): 안내 + 이동/재확인 버튼.
class AvatarSelectScreen extends StatefulWidget {
  const AvatarSelectScreen({
    super.key,
    this.currentStep = 12,
    this.totalSteps = 12,
    this.controller,
    this.completeOnboarding,
    this.onFinished,
    this.onStartOver,
    this.onBack,
  });

  final int currentStep;
  final int totalSteps;

  /// 테스트 주입용. 기본은 앱 루트 Provider 의 컨트롤러.
  final AvatarGenerationSessionController? controller;

  /// 승인 뒤 온보딩 완료 기록. 기본은 [OnboardingSaveHelper.completeOnboarding].
  final Future<void> Function()? completeOnboarding;

  /// 온보딩 완료 뒤 이동. 기본은 튜토리얼로 pushReplacement.
  final VoidCallback? onFinished;

  /// "사진을 바꾸고 다시 만들기" 뒤 이동. 기본은 사진 화면으로 pushReplacement.
  final VoidCallback? onStartOver;

  final VoidCallback? onBack;

  @override
  State<AvatarSelectScreen> createState() => _AvatarSelectScreenState();
}

class _AvatarSelectScreenState extends State<AvatarSelectScreen> {
  static const Duration _candidateRetryDelay = Duration(seconds: 2);

  AvatarGenerationSessionController? _injectedController;
  AvatarGenerationSessionController? _resolvedController;

  List<AvatarCandidate> _candidates = const [];
  String _candidatesForJobId = '';
  bool _loadingCandidates = false;
  bool _isApproving = false;
  bool _isFinishing = false;
  bool _isActionInFlight = false;
  String? _approvalError;
  String? _actionError;
  Timer? _candidateRetryTimer;

  AvatarGenerationSessionController get _controller {
    final resolved = _resolvedController;
    if (resolved != null) return resolved;
    final injected = _injectedController ?? widget.controller;
    final controller =
        injected ?? context.read<AvatarGenerationSessionController>();
    _resolvedController = controller;
    return controller;
  }

  AvatarGenerationClient get _client => _controller.client;

  @override
  void initState() {
    super.initState();
    _injectedController = widget.controller;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_resolvedController != null) return;
    final controller = _controller;
    controller.addListener(_onControllerChanged);
    // 첫 프레임에서는 컨트롤러가 이미 아는 상태로 그리고, 시작/재조회는
    // 프레임 뒤에 건다(build 중 setState 방지).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(controller.ensureStarted());
      unawaited(controller.refresh());
      _onControllerChanged();
    });
  }

  @override
  void dispose() {
    _candidateRetryTimer?.cancel();
    _resolvedController?.removeListener(_onControllerChanged);
    super.dispose();
  }

  void _onControllerChanged() {
    if (!mounted) return;
    final controller = _controller;
    switch (controller.phase) {
      case AvatarSessionPhase.previewReady:
        // 마지막 화면에 있으면 배너 대신 선택 UI 가 곧바로 뜬다.
        if (controller.completionBannerPending) controller.markBannerShown();
        if (_candidatesForJobId != controller.jobId) {
          _candidates = const [];
          _candidatesForJobId = '';
        }
        if (_candidates.isEmpty) unawaited(_loadCandidates());
        break;
      case AvatarSessionPhase.approved:
        unawaited(_finishOnboarding());
        break;
      case AvatarSessionPhase.idle:
      case AvatarSessionPhase.generating:
      case AvatarSessionPhase.attention:
      case AvatarSessionPhase.unavailable:
        _candidateRetryTimer?.cancel();
        break;
    }
    setState(() {});
  }

  Future<void> _loadCandidates() async {
    if (_loadingCandidates) return;
    final jobId = _controller.jobId;
    if (jobId.isEmpty) return;
    _loadingCandidates = true;
    try {
      final result = await _client.getCandidates(jobId);
      if (!mounted) return;
      if ((result.status == AvatarJobStatus.previewReady ||
              result.status == AvatarJobStatus.needsReview) &&
          result.candidates.isNotEmpty) {
        setState(() {
          _candidates = result.candidates;
          _candidatesForJobId = jobId;
        });
        return;
      }
      // 서버 상태와 후보 조회가 잠깐 어긋났다. 상태를 다시 읽고 잠시 뒤 재조회.
      _scheduleCandidateRetry();
    } catch (error) {
      _log('avatar_select_candidates_failed', error: error);
      if (!mounted) return;
      _scheduleCandidateRetry();
    } finally {
      _loadingCandidates = false;
    }
  }

  void _scheduleCandidateRetry() {
    _candidateRetryTimer?.cancel();
    _candidateRetryTimer = Timer(_candidateRetryDelay, () {
      if (!mounted) return;
      unawaited(_controller.refresh());
      if (_controller.phase == AvatarSessionPhase.previewReady &&
          _candidates.isEmpty) {
        unawaited(_loadCandidates());
      }
    });
  }

  Future<void> _approve(AvatarCandidate candidate) async {
    if (_isApproving || _isFinishing) return;
    setState(() {
      _isApproving = true;
      _approvalError = null;
    });
    try {
      final approval = await _client.approveCandidate(candidate.candidateId);
      if (!mounted) return;
      if (!approval.isApproved) {
        throw Exception('avatar_status_not_approved');
      }
      await _finishOnboarding();
    } catch (error) {
      _log('avatar_select_approval_failed', error: error);
      if (!mounted) return;
      setState(() {
        _isApproving = false;
        _approvalError = avatarSelectApprovalErrorMessage;
      });
    }
  }

  Future<void> _finishOnboarding() async {
    if (_isFinishing) return;
    _isFinishing = true;
    try {
      final complete =
          widget.completeOnboarding ?? OnboardingSaveHelper.completeOnboarding;
      await complete();
      if (!mounted) return;
      final onFinished = widget.onFinished;
      if (onFinished != null) {
        onFinished();
      } else {
        Navigator.of(
          context,
          rootNavigator: true,
        ).pushReplacementNamed(RouteNames.welcomeTutorial);
      }
    } catch (error) {
      _log('avatar_select_complete_failed', error: error);
      _isFinishing = false;
      if (!mounted) return;
      setState(() {
        _isApproving = false;
        _approvalError = avatarSelectApprovalErrorMessage;
      });
    }
  }

  Future<void> _retry() async {
    if (_isActionInFlight) return;
    final plan = _controller.plan;
    if (plan == null || !plan.retryAllowed) return;
    setState(() {
      _isActionInFlight = true;
      _actionError = null;
    });
    try {
      final retried = await _client.retryCurrentGeneration(
        clientRequestId: AvatarSourcePhotoService.createClientRequestId(),
      );
      if (!mounted) return;
      if (retried != null && retried.jobId.isNotEmpty) {
        await _controller.adoptJob(retried.jobId);
      } else {
        await _controller.refresh();
      }
    } catch (error) {
      _log('avatar_select_retry_failed', error: error);
      if (!mounted) return;
      setState(() => _actionError = avatarGenerationFailedMessage);
      unawaited(_controller.refresh());
    } finally {
      if (mounted) setState(() => _isActionInFlight = false);
    }
  }

  Future<void> _startOver() async {
    if (_isActionInFlight) return;
    final plan = _controller.plan;
    if (plan == null || !plan.allowsNewGeneration) return;
    setState(() {
      _isActionInFlight = true;
      _actionError = null;
    });
    try {
      final released = await _client.replaceCurrentGeneration(
        clientRequestId: AvatarSourcePhotoService.createClientRequestId(),
      );
      if (!mounted) return;
      if (!released) {
        setState(() => _actionError = avatarStartOverUnavailableMessage);
        return;
      }
      _controller.reset();
      if (!mounted) return;
      _goToPhotos();
    } catch (error) {
      _log('avatar_select_start_over_failed', error: error);
      if (!mounted) return;
      setState(() => _actionError = avatarStartOverUnavailableMessage);
    } finally {
      if (mounted) setState(() => _isActionInFlight = false);
    }
  }

  void _goToPhotos() {
    final onStartOver = widget.onStartOver;
    if (onStartOver != null) {
      onStartOver();
      return;
    }
    Navigator.of(context).pushReplacementNamed(RouteNames.onboardingPhoto);
  }

  void _handleBack() {
    HapticFeedback.lightImpact();
    if (widget.onBack != null) {
      widget.onBack!();
    } else if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  void _log(String phase, {Object? error}) {
    final parts = <String>['[AvatarFlow]', phase];
    if (error != null) {
      parts.add('error=${PrivacyLogUtils.errorSummary(error)}');
    }
    debugPrint(parts.join(' '));
  }

  @override
  Widget build(BuildContext context) {
    final controller = _resolvedController ?? widget.controller;
    final phase = controller?.phase ?? AvatarSessionPhase.generating;
    final showSelection =
        phase == AvatarSessionPhase.previewReady && _candidates.isNotEmpty;
    final showWaiting =
        phase == AvatarSessionPhase.generating ||
        phase == AvatarSessionPhase.approved ||
        (phase == AvatarSessionPhase.previewReady && _candidates.isEmpty);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        _handleBack();
      },
      child: Scaffold(
        backgroundColor: _AppColors.backgroundLight,
        body: SafeArea(
          child: Stack(
            children: [
              Column(
                children: [
                  _Header(
                    currentStep: widget.currentStep,
                    totalSteps: widget.totalSteps,
                    onBack: _handleBack,
                  ),
                  Expanded(
                    child: showSelection
                        ? AvatarCandidateSelectionDialog(
                            key: const ValueKey('avatar_select_candidates'),
                            candidates: _candidates,
                            isApproving: _isApproving,
                            errorMessage: _approvalError,
                            onConfirm: _approve,
                          )
                        : _buildBody(controller, phase),
                  ),
                ],
              ),
              IgnorePointer(
                ignoring: !showWaiting,
                child: AvatarGeneratingOverlay(visible: showWaiting),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(
    AvatarGenerationSessionController? controller,
    AvatarSessionPhase phase,
  ) {
    switch (phase) {
      case AvatarSessionPhase.generating:
      case AvatarSessionPhase.approved:
      case AvatarSessionPhase.previewReady:
        return const _WaitingBody();
      case AvatarSessionPhase.attention:
        final plan = controller?.plan;
        return _AttentionBody(
          message: plan?.message.isNotEmpty == true
              ? plan!.message
              : avatarGenerationFailedMessage,
          actionError: _actionError,
          isBusy: _isActionInFlight,
          onRetry: plan?.retryAllowed == true ? _retry : null,
          onStartOver: plan?.allowsNewGeneration == true ? _startOver : null,
        );
      case AvatarSessionPhase.idle:
        return _AttentionBody(
          message: avatarSelectNoJobMessage,
          actionError: _actionError,
          isBusy: _isActionInFlight,
          primaryLabel: avatarSelectGoToPhotosLabel,
          onPrimary: _goToPhotos,
        );
      case AvatarSessionPhase.unavailable:
        return _AttentionBody(
          message: avatarSelectStatusUnavailableMessage,
          actionError: _actionError,
          isBusy: _isActionInFlight,
          primaryLabel: avatarSelectCheckAgainLabel,
          onPrimary: () => unawaited(_controller.refresh()),
        );
    }
  }
}

class _WaitingBody extends StatelessWidget {
  const _WaitingBody();

  @override
  Widget build(BuildContext context) {
    // 실제 대기 UI 는 AvatarGeneratingOverlay 가 화면 전체에 그린다.
    return const SizedBox.expand();
  }
}

class _AttentionBody extends StatelessWidget {
  const _AttentionBody({
    required this.message,
    required this.isBusy,
    this.actionError,
    this.onRetry,
    this.onStartOver,
    this.primaryLabel,
    this.onPrimary,
  });

  final String message;
  final String? actionError;
  final bool isBusy;
  final Future<void> Function()? onRetry;
  final Future<void> Function()? onStartOver;
  final String? primaryLabel;
  final VoidCallback? onPrimary;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            '아바타 확인이 필요해요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 26,
              fontWeight: FontWeight.bold,
              color: _AppColors.textMain,
              height: 1.3,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: _AppColors.progressBg),
            ),
            child: Text(
              message,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                color: _AppColors.textMain,
                height: 1.5,
              ),
            ),
          ),
          if (actionError != null) ...[
            const SizedBox(height: 12),
            Text(
              actionError!,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                color: Color(0xFFB42352),
                height: 1.4,
              ),
            ),
          ],
          const SizedBox(height: 24),
          if (onRetry != null)
            _PrimaryButton(
              label: avatarSelectRetryLabel,
              enabled: !isBusy,
              onPressed: () => unawaited(onRetry!()),
            ),
          if (onStartOver != null) ...[
            if (onRetry != null) const SizedBox(height: 12),
            _SecondaryButton(
              label: avatarStartOverButtonLabel,
              enabled: !isBusy,
              onPressed: () => unawaited(onStartOver!()),
            ),
          ],
          if (primaryLabel != null && onPrimary != null)
            _PrimaryButton(
              label: primaryLabel!,
              enabled: !isBusy,
              onPressed: onPrimary!,
            ),
        ],
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    required this.label,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 54,
      child: ElevatedButton(
        onPressed: enabled ? onPressed : null,
        style: ElevatedButton.styleFrom(
          elevation: 0,
          backgroundColor: _AppColors.primary,
          disabledBackgroundColor: _AppColors.primary.withValues(alpha: 0.35),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        child: Text(
          label,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}

class _SecondaryButton extends StatelessWidget {
  const _SecondaryButton({
    required this.label,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 54,
      child: OutlinedButton(
        onPressed: enabled ? onPressed : null,
        style: OutlinedButton.styleFrom(
          foregroundColor: _AppColors.primary,
          side: const BorderSide(color: _AppColors.primary),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        child: Text(
          label,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback onBack;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    required this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight.withValues(alpha: 0.8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: onBack,
            icon: const Icon(
              Icons.arrow_back_rounded,
              color: _AppColors.textMain,
              size: 24,
            ),
            style: IconButton.styleFrom(
              padding: const EdgeInsets.all(8),
              backgroundColor: Colors.transparent,
            ),
          ),
          Row(
            children: List.generate(totalSteps, (index) {
              final isCurrent = index == currentStep - 1;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: isCurrent ? 24 : 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: isCurrent ? _AppColors.primary : _AppColors.progressBg,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}
