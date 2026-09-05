import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/avatar_generation_client.dart';
import '../../../services/avatar_source_photo_service.dart';
import '../../../services/onboarding_photo_upload_service.dart';
import '../../../services/onboarding_photo_source_ref.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/utils/avatar_lock_policy.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../../../shared/widgets/profile_photo_mosaic.dart';
import '../services/avatar_resume_policy.dart';
import '../services/avatar_upload_submission_guard.dart';
import '../widgets/avatar_candidate_selection_dialog.dart';
import '../widgets/avatar_generation_error_banner.dart';
import '../widgets/avatar_generating_overlay.dart';
import '../widgets/avatar_generation_messages.dart';
import '../widgets/avatar_generation_models.dart';

class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF89616F);
  static const Color textGray = Color(0xFF9CA3AF);
  static const Color borderDashed = Color(0xFFE6DBDF);
  static const Color progressBg = Color(0xFFE6DBDF);
}

class PhotoUploadScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final Function(List<String> photos)? onNext;

  /// 아바타 생성/승인 흐름을 담당하는 클라이언트. 기본값은 백엔드 콜러블을
  /// 호출하는 [BackendAvatarGenerationClient]이며, 위젯 테스트/디자인 QA에서만
  /// [MockAvatarGenerationClient]를 주입해 사용합니다.
  final AvatarGenerationClient? avatarGenerationClient;
  final OnboardingPhotoUploadService? onboardingPhotoUploadService;

  /// Test-only initial slot values for exercising the avatar polling and
  /// approval flow without invoking the image picker or Firebase upload.
  final List<String?>? initialPhotosForTesting;

  /// Test-only picked-file seeds matching [initialPhotosForTesting] slots,
  /// used to exercise the fresh generation path without the image picker.
  final List<XFile?>? initialPickedFilesForTesting;
  final List<OnboardingPhotoSourceRef?>? initialSourceRefsForTesting;

  /// Test-only approved-avatar lock seed. Production lock state always comes
  /// from the server profile via [avatarLockStateFromUserProfile].
  final String? lockedApprovedAvatarUrlForTesting;

  const PhotoUploadScreen({
    super.key,
    this.currentStep = 6,
    this.totalSteps = 9,
    this.onBack,
    this.onNext,
    this.avatarGenerationClient,
    this.onboardingPhotoUploadService,
    this.initialPhotosForTesting,
    this.initialPickedFilesForTesting,
    this.initialSourceRefsForTesting,
    this.lockedApprovedAvatarUrlForTesting,
  });

  @override
  State<PhotoUploadScreen> createState() => _PhotoUploadScreenState();
}

class _PhotoUploadScreenState extends State<PhotoUploadScreen> {
  static const int _requiredPhotoCount = 2;
  static const Duration _avatarPollInterval = Duration(seconds: 2);
  static const Duration _avatarPollTimeout = Duration(seconds: 300);
  // 서버가 여전히 활성 상태라면 클라이언트 데드라인을 이만큼 연장한다.
  static const int _maxAvatarPollExtensions = 2;

  final ImagePicker _imagePicker = ImagePicker();

  final List<String?> _photos = List<String?>.filled(6, null);
  final List<XFile?> _pickedFiles = List<XFile?>.filled(6, null);
  final List<OnboardingPhotoSourceRef?> _serverSourceRefs =
      List<OnboardingPhotoSourceRef?>.filled(6, null);
  final List<bool> _isUploading = List<bool>.filled(6, false);
  final AvatarUploadSubmissionGuard _uploadSubmissionGuard =
      AvatarUploadSubmissionGuard();
  String? _sourceUploadRequestId;
  bool _isHandlingNext = false;

  AuthService? _authService;
  OnboardingPhotoUploadService? _onboardingPhotoUploadService;
  StorageService? _storageService;
  UserService? _userService;

  late final AvatarGenerationClient _avatarClient;
  AvatarOnboardingFlowState _avatarFlowState = AvatarOnboardingFlowState.idle;
  List<AvatarCandidate> _candidates = const [];
  String? _avatarGenerationError;
  String? _avatarApprovalError;
  bool _isCandidateDialogOpen = false;
  bool _avatarFlowCancelled = false;
  bool _chatPartnerRealPhotoDisclosure = false;
  bool _avatarLocked = false;
  bool _avatarSourceLocked = false;
  String _lockedApprovedAvatarUrl = '';
  String? _activeAvatarJobId;
  String? _activeAvatarSourcePhotoId;
  int? _activeSourceSelectionVersion;
  bool _avatarRetryAllowed = true;
  // needs_review / 최종 실패에서 "사진을 바꾸고 다시 만들기"를 허용하는가.
  // 재시도와 다른 축이며, provider 결과 미확인 상태에서는 둘 다 false 다.
  bool _avatarAllowsNewGeneration = false;
  int _avatarPollExtensions = 0;

  int get _photoCount => _photos.where((p) => p != null).length;

  // 사진 최소 장수는 production 계약이며 빌드 플래그로 완화할 수 없다.
  int get _minRequiredPhotos => _requiredPhotoCount;

  // 승인된 아바타 보유 여부는 서버 프로필에서 파생된 잠금 상태만 신뢰한다.
  // 슬롯 문자열 검사로 판정하면 일반 사진 URL이 승인으로 오인된다.
  bool get _hasApprovedAvatarForProceed => _avatarLocked;

  bool get _isAvatarFlowActive =>
      _avatarFlowState != AvatarOnboardingFlowState.idle &&
      _avatarFlowState != AvatarOnboardingFlowState.approved &&
      _avatarFlowState != AvatarOnboardingFlowState.failed;

  bool get _hasStartedAvatarSourceLock =>
      _avatarSourceLocked ||
      (_activeAvatarJobId != null && _activeAvatarJobId!.isNotEmpty);

  bool get _isSourceMutationBlocked =>
      _avatarLocked ||
      _hasStartedAvatarSourceLock ||
      _isAvatarFlowActive ||
      _isUploading.any((value) => value);

  bool get _isGenerating =>
      _avatarFlowState == AvatarOnboardingFlowState.uploadingSourcePhoto ||
      _avatarFlowState == AvatarOnboardingFlowState.avatarQueued ||
      _avatarFlowState == AvatarOnboardingFlowState.generatingAvatar;

  AuthService get _auth => _authService ??= AuthService();

  OnboardingPhotoUploadService get _onboardingPhotoService =>
      _onboardingPhotoUploadService ??=
          widget.onboardingPhotoUploadService ?? OnboardingPhotoUploadService();

  StorageService get _storage => _storageService ??= StorageService();

  UserService get _users => _userService ??= UserService();

  @override
  void initState() {
    super.initState();
    _avatarClient =
        widget.avatarGenerationClient ?? BackendAvatarGenerationClient();
    final initialPhotos = widget.initialPhotosForTesting;
    if (initialPhotos != null) {
      for (int i = 0; i < initialPhotos.length && i < _photos.length; i++) {
        _photos[i] = initialPhotos[i];
      }
      final initialPickedFiles = widget.initialPickedFilesForTesting;
      if (initialPickedFiles != null) {
        for (
          int i = 0;
          i < initialPickedFiles.length && i < _pickedFiles.length;
          i++
        ) {
          _pickedFiles[i] = initialPickedFiles[i];
        }
      }
      final initialSourceRefs = widget.initialSourceRefsForTesting;
      if (initialSourceRefs != null) {
        for (
          int i = 0;
          i < initialSourceRefs.length && i < _serverSourceRefs.length;
          i++
        ) {
          _serverSourceRefs[i] = initialSourceRefs[i];
        }
      }
      final lockedUrl = widget.lockedApprovedAvatarUrlForTesting?.trim() ?? '';
      _avatarLocked =
          lockedUrl.isNotEmpty && isSafePublicApprovedAvatarUrl(lockedUrl);
      _lockedApprovedAvatarUrl = _avatarLocked ? lockedUrl : '';
      if (_serverSourceRefs.whereType<OnboardingPhotoSourceRef>().length <
          _requiredPhotoCount) {
        for (final value in initialPhotos.whereType<String>()) {
          final queuedJobId = AvatarSourcePhotoService.queuedJobId(value);
          if (queuedJobId != null && queuedJobId.isNotEmpty) {
            _activeAvatarJobId = queuedJobId;
            _avatarSourceLocked = true;
          }
        }
      }
      // 서버 상태는 사진 시드 경로와 무관하게 항상 복구 권위다.
      unawaited(_resumeFromServerStatus());
    } else {
      _loadExistingPhotos();
    }
  }

  @override
  void dispose() {
    _avatarFlowCancelled = true;
    super.dispose();
  }

  Future<void> _loadExistingPhotos() async {
    final kakaoUserId = await _storage.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final data = await _users.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;

    final profile = Map<String, dynamic>.from(data);
    final lockState = avatarLockStateFromUserProfile(profile);
    final sourceLocked = avatarSourceLockedFromUserProfile(profile);
    final sourceJobId = avatarSourceJobIdFromUserProfile(profile);
    final sourceSelectionVersion = avatarSourceSelectionVersionFromUserProfile(
      profile,
    );
    final onboarding = data['onboarding'];
    final avatarUrlsRaw = onboarding is Map ? onboarding['avatarUrls'] : null;
    final avatarUrls =
        lockState.isLocked && lockState.approvedAvatarUrl.isNotEmpty
        ? <String>[lockState.approvedAvatarUrl]
        : avatarUrlsRaw is List
        ? avatarUrlsRaw.whereType<String>().toList()
        : <String>[];

    setState(() {
      _avatarLocked = lockState.isLocked;
      _avatarSourceLocked = !lockState.isLocked && sourceLocked;
      _lockedApprovedAvatarUrl = lockState.approvedAvatarUrl;
      if (_avatarSourceLocked && sourceJobId != null) {
        _activeAvatarJobId = sourceJobId;
        _activeSourceSelectionVersion = sourceSelectionVersion;
      }
      for (int i = 0; i < _photos.length; i++) {
        _photos[i] = null;
      }
      for (int i = 0; i < avatarUrls.length && i < _photos.length; i++) {
        _photos[i] = avatarUrls[i];
      }
      if (_avatarSourceLocked &&
          sourceJobId != null &&
          !_photos.any(AvatarSourcePhotoService.isQueuedSlotToken)) {
        _photos[0] = AvatarSourcePhotoService.queuedSlotToken(sourceJobId);
      }
    });

    await _resumeFromServerStatus();
  }

  /// 서버 상태를 권위로 삼아 화면을 복구한다.
  ///
  /// 화면 로컬 사진 개수로 복구를 판단하면, 생성 중 재시작 시 합성 슬롯 1개만
  /// 남아 "다음"이 비활성화되고 소스 잠금 때문에 사진도 추가할 수 없는 교착이
  /// 생긴다. 진행 중인 작업이 있으면 곧바로 생성 화면으로 되돌린다.
  Future<void> _resumeFromServerStatus() async {
    final snapshot = await _avatarClient.getCurrentGenerationStatus();
    if (!mounted) return;
    final plan = planAvatarResume(snapshot);
    _logAvatarFlow(
      'avatar_resume_plan',
      jobId: plan.jobId,
      rawStatus: plan.action.name,
    );

    switch (plan.action) {
      case AvatarResumeAction.unavailable:
      case AvatarResumeAction.none:
        return;
      case AvatarResumeAction.resumeApproved:
        setState(() {
          _avatarLocked = true;
          _avatarFlowState = AvatarOnboardingFlowState.approved;
        });
        return;
      case AvatarResumeAction.resumeGenerating:
      case AvatarResumeAction.resumePreview:
        if (plan.jobId.isEmpty) return;
        setState(() {
          _activeAvatarJobId = plan.jobId;
          _avatarSourceLocked = true;
          _avatarGenerationError = null;
          _avatarRetryAllowed = true;
        });
        _avatarPollExtensions = 0;
        await _startAvatarGeneration();
        return;
      case AvatarResumeAction.showRetryable:
      case AvatarResumeAction.showNeedsReview:
      case AvatarResumeAction.showTerminal:
      // provider 결과 미확인 상태. 재시도 버튼을 제공하지 않는다.
      case AvatarResumeAction.showReconciliation:
        setState(() {
          if (plan.jobId.isNotEmpty) _activeAvatarJobId = plan.jobId;
          _avatarSourceLocked = true;
          _avatarRetryAllowed = plan.retryAllowed;
          _avatarAllowsNewGeneration = plan.allowsNewGeneration;
          _avatarGenerationError = plan.message;
          _avatarFlowState = AvatarOnboardingFlowState.failed;
        });
        return;
    }
  }

  /// 재시도 버튼 진입점. 한 프레임 안에 두 번 눌려도 폴링 루프가 두 개
  /// 생기지 않도록 "다음" 버튼과 동일한 재진입 가드를 공유한다.
  ///
  /// 재시도 가능 여부의 권위는 서버다. 서버가 허용한 실패는 서버 재시도
  /// 콜러블(같은 logical generation 재디스패치)을 거치고, 진행 중이면 폴링만
  /// 잇는다. 서버가 거부하면 재시도 없이 그 이유를 보여준다.
  Future<void> _handleAvatarRetry() async {
    // 상태 가드: 재시도가 이미 소진/거부된 뒤 같은 프레임의 stale 버튼 탭을 막는다.
    if (!_avatarRetryAllowed) return;
    if (_isAvatarFlowActive || _isHandlingNext) return;
    _isHandlingNext = true;
    try {
      _avatarPollExtensions = 0;
      final jobId = _findPrimaryAvatarJobId();
      if (jobId != null) {
        final snapshot = await _avatarClient.getCurrentGenerationStatus();
        if (!mounted) return;
        final plan = planAvatarResume(snapshot);
        if (plan.action == AvatarResumeAction.showRetryable &&
            plan.retryAllowed) {
          final retried = await _avatarClient.retryCurrentGeneration(
            clientRequestId: AvatarSourcePhotoService.createClientRequestId(),
          );
          if (!mounted) return;
          if (retried != null && retried.jobId.isNotEmpty) {
            setState(() => _activeAvatarJobId = retried.jobId);
          }
        } else if (plan.action == AvatarResumeAction.showTerminal ||
            plan.action == AvatarResumeAction.showNeedsReview ||
            plan.action == AvatarResumeAction.showReconciliation) {
          _avatarRetryAllowed = false;
          _avatarAllowsNewGeneration = plan.allowsNewGeneration;
          _failAvatarGeneration(
            plan.message,
            phase: 'avatar_retry_refused_by_server',
            jobId: jobId,
          );
          return;
        }
      }
      await _startAvatarGeneration();
    } finally {
      _isHandlingNext = false;
    }
  }

  /// "사진을 바꾸고 다시 만들기". 같은 generation 재시도가 아니라 현재 generation
  /// 을 서버에서 종료하고 source lock 을 푼 뒤, 새 사진 세트로 새 generation
  /// (새 clientRequestId, 새 source selection, 새 jobId) 을 연다.
  Future<void> _handleStartOverWithNewPhotos() async {
    // 상태 가드: 첫 탭이 이미 generation 을 종료했다면 리빌드 전의 두 번째
    // 탭은 아무것도 하지 않는다. 서버 호출은 정확히 한 번이다.
    if (!_avatarAllowsNewGeneration) return;
    if (_isAvatarFlowActive || _isHandlingNext) return;
    _isHandlingNext = true;
    try {
      final released = await _avatarClient.replaceCurrentGeneration(
        clientRequestId: AvatarSourcePhotoService.createClientRequestId(),
      );
      if (!mounted) return;
      if (!released) {
        _showErrorSnack(avatarStartOverUnavailableMessage);
        return;
      }
      setState(() {
        _activeAvatarJobId = null;
        _activeAvatarSourcePhotoId = null;
        _activeSourceSelectionVersion = null;
        _avatarSourceLocked = false;
        _avatarGenerationError = null;
        _avatarRetryAllowed = true;
        _avatarAllowsNewGeneration = false;
        _sourceUploadRequestId = null;
        _avatarFlowState = AvatarOnboardingFlowState.idle;
        for (var i = 0; i < _photos.length; i++) {
          if (AvatarSourcePhotoService.isQueuedSlotToken(_photos[i])) {
            _photos[i] = null;
            _serverSourceRefs[i] = null;
          }
        }
      });
      _logAvatarFlow('avatar_generation_replaced');
    } finally {
      _isHandlingNext = false;
    }
  }

  Future<void> _addPhoto(int index) async {
    if (!_uploadSubmissionGuard.tryAcquire(index)) return;
    try {
      HapticFeedback.lightImpact();
      if (_avatarLocked) {
        _showLockedAvatarMessage();
        return;
      }
      if (_isSourceMutationBlocked) {
        _showSourceLockedAvatarMessage();
        return;
      }

      if (mounted) {
        setState(() {
          _isUploading[index] = true;
          _avatarFlowCancelled = true;
        });
      }

      final XFile? pickedFile = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 88,
      );

      if (pickedFile == null) {
        return;
      }

      final String? kakaoUserId = await _storage.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.');
      }

      final hasFirebaseSession = await _auth.ensureCanonicalAppSession();
      if (!hasFirebaseSession) {
        throw Exception(
          'Firebase login session is required for private upload.',
        );
      }

      // 사진은 슬롯마다 서버 검증 업로드로 먼저 확보하고, 아바타 생성 소스
      // 업로드(잠금 시작)는 "다음" 시점으로 미룬다. 그래야 2장 요구사항을
      // 채우기 전에 소스 잠금이 걸리는 교착이 생기지 않는다.
      final result = await _onboardingPhotoService.uploadPickedImage(
        file: pickedFile,
        slotIndex: index,
        uid: kakaoUserId,
      );
      if (!mounted) return;

      setState(() {
        _photos[index] = result.photoUrl;
        _pickedFiles[index] = pickedFile;
        _serverSourceRefs[index] = result.sourceRef;
        _avatarFlowCancelled = false;
        _avatarGenerationError = null;
      });
    } catch (e) {
      _logAvatarFlow('avatar_upload_failed', slotIndex: index, error: e);
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('사진 업로드에 실패했어요. 잠시 후 다시 시도해주세요.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      _uploadSubmissionGuard.release(index);
      if (mounted && _isUploading[index]) {
        setState(() => _isUploading[index] = false);
      }
    }
  }

  void _removePhoto(int index) {
    HapticFeedback.lightImpact();
    if (_avatarLocked) {
      _showLockedAvatarMessage();
      return;
    }
    if (_isSourceMutationBlocked) {
      _showSourceLockedAvatarMessage();
      return;
    }
    setState(() {
      final removedJobId = AvatarSourcePhotoService.queuedJobId(_photos[index]);
      if (removedJobId != null && removedJobId == _activeAvatarJobId) {
        _activeAvatarJobId = null;
        _activeAvatarSourcePhotoId = null;
        _activeSourceSelectionVersion = null;
        _avatarFlowCancelled = true;
      }
      _photos[index] = null;
      _pickedFiles[index] = null;
      _serverSourceRefs[index] = null;
      _isUploading[index] = false;
      _avatarGenerationError = null;
    });
  }

  void _showLockedAvatarMessage() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(lockedAvatarMessage),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  void _showSourceLockedAvatarMessage() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(sourceLockedAvatarMessage),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _handleNext() async {
    if (_isAvatarFlowActive || _isHandlingNext) {
      return;
    }
    _isHandlingNext = true;
    try {
      if (!_hasApprovedAvatarForProceed && _photoCount < _minRequiredPhotos) {
        HapticFeedback.heavyImpact();
        _showErrorSnack('사진을 최소 2장 이상 등록해주세요.');
        return;
      }

      if (_isUploading.any((e) => e)) {
        HapticFeedback.heavyImpact();
        _showErrorSnack('사진 업로드가 끝난 뒤 다음으로 넘어가주세요.');
        return;
      }

      HapticFeedback.mediumImpact();
      if (_avatarLocked) {
        // 이미 승인된 아바타가 있는 재방문 사용자만 생성 없이 진행한다.
        await _goToSelfIntroduction();
        return;
      }
      await _startAvatarGeneration();
    } finally {
      _isHandlingNext = false;
    }
  }

  String? _findPrimaryAvatarJobId() {
    final jobId = _activeAvatarJobId;
    return jobId == null || jobId.isEmpty ? null : jobId;
  }

  Future<void> _startAvatarGeneration() async {
    String? jobId = _findPrimaryAvatarJobId();
    if (jobId == null) {
      if (_hasStartedAvatarSourceLock) {
        _failAvatarGeneration(
          sourceLockedAvatarFailureMessage,
          phase: 'avatar_source_locked_missing_job',
        );
        return;
      }
      jobId = await _beginAvatarGenerationFromUploadedPhotos();
      if (jobId == null) {
        return;
      }
    }

    if (!mounted) return;
    setState(() {
      _avatarFlowCancelled = false;
      _avatarGenerationError = null;
      _avatarApprovalError = null;
      _avatarRetryAllowed = true;
      _avatarAllowsNewGeneration = false;
      _candidates = const [];
      _avatarFlowState = AvatarOnboardingFlowState.generatingAvatar;
    });
    _logAvatarFlow(
      'avatar_poll_start',
      jobId: jobId,
      photoId: _activeAvatarSourcePhotoId,
      sourceSelectionVersion: _activeSourceSelectionVersion,
    );

    try {
      final result = await _avatarClient.pollUntilPreviewReady(
        jobId: jobId,
        pollInterval: _avatarPollInterval,
        timeout: _avatarPollTimeout,
        shouldContinue: () => mounted && !_avatarFlowCancelled,
      );
      _logAvatarFlow(
        'avatar_poll_completed',
        jobId: jobId,
        status: result.status,
        candidateCount: result.candidates.length,
      );

      if (!mounted || _avatarFlowCancelled) return;

      if (result.status == AvatarJobStatus.noPreviewableCandidates) {
        _avatarAllowsNewGeneration = true;
        _failAvatarGeneration(
          avatarGenerationFailureMessage(
            status: result.status,
            errorCode: result.errorCode,
          ),
          phase: 'avatar_poll_no_previewable_candidates',
          jobId: jobId,
        );
        return;
      }

      if (result.status == AvatarJobStatus.failed) {
        if (result.errorCode == 'avatar_no_eligible_source_photo') {
          _releaseRejectedSourceSelection();
        } else {
          _avatarAllowsNewGeneration = true;
        }
        _failAvatarGeneration(
          avatarGenerationFailureMessage(
            status: result.status,
            errorCode: result.errorCode,
          ),
          phase: 'avatar_poll_failed_status',
          jobId: jobId,
        );
        return;
      }

      if (result.status == AvatarJobStatus.needsReview) {
        // 생성은 성공했지만 자동 안전 검사를 통과하지 못했다. 같은 generation
        // 재시도는 없고, 사용자가 사진을 바꿔 새 generation 을 시작할 수 있다.
        _avatarRetryAllowed = false;
        _avatarAllowsNewGeneration = true;
        _failAvatarGeneration(
          avatarNeedsReviewMessage,
          phase: 'avatar_poll_needs_review',
          jobId: jobId,
        );
        return;
      }

      if (result.status == AvatarJobStatus.superseded ||
          result.status == AvatarJobStatus.cancelled) {
        _failAvatarGeneration(
          avatarGenerationFailureMessage(
            status: result.status,
            errorCode: result.errorCode,
          ),
          phase: 'avatar_poll_terminal_${result.status.name}',
          jobId: jobId,
        );
        return;
      }

      if (result.candidates.isEmpty) {
        _failAvatarGeneration(
          avatarGenericEmptyCandidateMessage,
          phase: 'avatar_poll_empty_candidates',
          jobId: jobId,
        );
        return;
      }

      setState(() {
        _candidates = result.candidates;
        _avatarFlowState = AvatarOnboardingFlowState.previewReady;
      });

      await _openCandidateDialog();
    } on AvatarPollingCancelled {
      // 위젯이 dispose되거나 사용자가 명시적으로 흐름을 중단한 경우.
    } on TimeoutException {
      if (!mounted) return;
      // 서버 작업이 계속 진행 중인데 클라이언트 타이머 하나로 최종 실패를
      // 만들면 안 된다. 서버 상태를 다시 확인해 활성 상태면 폴링을 연장한다.
      final snapshot = await _avatarClient.getCurrentGenerationStatus();
      if (!mounted || _avatarFlowCancelled) return;
      final plan = planAvatarResume(snapshot);
      final serverStillActive =
          plan.action == AvatarResumeAction.resumeGenerating ||
          plan.action == AvatarResumeAction.resumePreview;
      if (serverStillActive &&
          _avatarPollExtensions < _maxAvatarPollExtensions) {
        _avatarPollExtensions += 1;
        _logAvatarFlow(
          'avatar_poll_extended',
          jobId: jobId,
          rawStatus: '$_avatarPollExtensions',
        );
        await _startAvatarGeneration();
        return;
      }
      _failAvatarGeneration(
        avatarGenerationDelayedMessage,
        phase: 'avatar_poll_timeout',
        jobId: jobId,
      );
    } catch (e) {
      if (!mounted) return;
      _failAvatarGeneration(
        avatarGenerationFailedMessage,
        phase: 'avatar_poll_exception',
        jobId: jobId,
        error: e,
      );
    }
  }

  Future<String?> _beginAvatarGenerationFromUploadedPhotos() async {
    final verifiedSources =
        _serverSourceRefs.whereType<OnboardingPhotoSourceRef>().toList()
          ..sort((left, right) => left.slotIndex.compareTo(right.slotIndex));
    if (verifiedSources.length < _requiredPhotoCount) {
      // 서버가 source ref 를 돌려주지 않았다(구 백엔드 또는 구 세션). 예전처럼
      // 첫 사진으로 legacy generation 을 몰래 시작하지 않고 명확히 fail-closed
      // 한다. 해결은 배포 순서(Functions 먼저)이지 클라이언트 fallback 이 아니다.
      _avatarRetryAllowed = false;
      _avatarAllowsNewGeneration = false;
      _failAvatarGeneration(
        avatarBackendIncompatibleMessage,
        phase: 'avatar_source_refs_unavailable',
      );
      return null;
    }

    final kakaoUserId = (await _storage.getKakaoUserId()) ?? '';
    final clientRequestId = _sourceUploadRequestId ??=
        AvatarSourcePhotoService.createClientRequestId();
    if (!mounted) return null;
    setState(() {
      _avatarFlowState = AvatarOnboardingFlowState.uploadingSourcePhoto;
      _avatarFlowCancelled = false;
      _avatarGenerationError = null;
    });
    _logAvatarFlow('avatar_source_set_admission_start');

    try {
      final result = await _avatarClient.beginFromOnboardingPhotos(
        sourcePhotos: verifiedSources,
        uid: kakaoUserId,
        clientRequestId: clientRequestId,
        chatPartnerRealPhotoDisclosure: _chatPartnerRealPhotoDisclosure,
      );
      if (!mounted) return null;
      setState(() {
        _activeAvatarJobId = result.jobId;
        _activeAvatarSourcePhotoId = result.photoId.isEmpty
            ? null
            : result.photoId;
        _activeSourceSelectionVersion = result.sourceSelectionVersion;
        _avatarSourceLocked = true;
      });
      _logAvatarFlow(
        'avatar_source_set_admission_success',
        jobId: result.jobId,
        sourceSelectionVersion: result.sourceSelectionVersion,
      );
      return result.jobId;
    } on AvatarAlreadyApprovedException {
      await _loadExistingPhotos();
      if (!mounted) return null;
      if (_avatarLocked) {
        setState(() => _avatarFlowState = AvatarOnboardingFlowState.approved);
        await _goToSelfIntroduction();
      } else {
        _failAvatarGeneration(
          AvatarAlreadyApprovedException.message,
          phase: 'avatar_source_set_already_approved',
        );
      }
      return null;
    } on AvatarSourceLockedException {
      await _loadExistingPhotos();
      if (!mounted) return null;
      final resumedJobId = _findPrimaryAvatarJobId();
      if (resumedJobId != null) return resumedJobId;
      _failAvatarGeneration(
        sourceLockedAvatarFailureMessage,
        phase: 'avatar_source_set_locked_missing_job',
      );
      return null;
    } on FirebaseFunctionsException catch (error) {
      _failAvatarGeneration(
        _sourceUploadFailureMessage(error),
        phase: 'avatar_source_set_rejected',
        error: error,
      );
      return null;
    } catch (error) {
      _failAvatarGeneration(
        avatarGenerationFailedMessage,
        phase: 'avatar_source_set_failed',
        error: error,
      );
      return null;
    }
  }

  // 단일 사진 legacy generation 경로는 존재하지 않는다.
  // canonical 경로는 beginAvatarGenerationFromOnboardingPhotos 하나뿐이다.

  String _sourceUploadFailureMessage(FirebaseFunctionsException error) {
    final detail = '${error.message ?? ''} ${error.details ?? ''}';
    if (detail.contains('avatar_minimum_photos_required')) {
      return avatarMinimumPhotosMessage;
    }
    if (detail.contains('avatar_source_set_invalid') ||
        detail.contains('avatar_onboarding_source_invalid') ||
        detail.contains('avatar_onboarding_source_generation_mismatch')) {
      return avatarSourceSetInvalidMessage;
    }
    if (detail.contains('avatar_legacy_generation_start_disabled')) {
      return avatarBackendIncompatibleMessage;
    }
    if (detail.contains('avatar_generation_paused') ||
        detail.contains('avatar_budget_exceeded') ||
        detail.contains('avatar_generation_not_open')) {
      return avatarGenerationPausedMessage;
    }
    return avatarGenerationFailedMessage;
  }

  Future<void> _openCandidateDialog() async {
    if (!mounted) return;
    if (_isCandidateDialogOpen) return;
    _isCandidateDialogOpen = true;
    try {
      await showGeneralDialog<void>(
        context: context,
        barrierDismissible: false,
        barrierColor: Colors.transparent,
        useRootNavigator: false,
        transitionDuration: const Duration(milliseconds: 240),
        transitionBuilder: (context, animation, secondary, child) {
          final curve = CurvedAnimation(
            parent: animation,
            curve: Curves.easeOutCubic,
          );
          return FadeTransition(
            opacity: curve,
            child: ScaleTransition(
              scale: Tween<double>(begin: 0.96, end: 1.0).animate(curve),
              child: child,
            ),
          );
        },
        pageBuilder: (dialogContext, animation, secondary) {
          return PopScope(
            canPop: false,
            child: StatefulBuilder(
              builder: (ctx, setDialogState) {
                return AvatarCandidateSelectionDialog(
                  candidates: _candidates,
                  isApproving:
                      _avatarFlowState ==
                      AvatarOnboardingFlowState.approvingAvatar,
                  errorMessage: _avatarApprovalError,
                  onConfirm: (candidate) async {
                    setDialogState(() {});
                    await _approveAvatarCandidate(
                      candidate: candidate,
                      dialogContext: dialogContext,
                      refreshDialog: setDialogState,
                    );
                  },
                );
              },
            ),
          );
        },
      );
    } finally {
      _isCandidateDialogOpen = false;
    }
  }

  Future<void> _approveAvatarCandidate({
    required AvatarCandidate candidate,
    required BuildContext dialogContext,
    required void Function(VoidCallback) refreshDialog,
  }) async {
    if (_avatarFlowState == AvatarOnboardingFlowState.approvingAvatar) return;

    setState(() {
      _avatarApprovalError = null;
      _avatarFlowState = AvatarOnboardingFlowState.approvingAvatar;
    });
    refreshDialog(() {});

    try {
      final approval = await _avatarClient.approveCandidate(
        candidate.candidateId,
      );

      if (!mounted) return;

      if (!approval.isApproved) {
        throw Exception('avatar_status_not_approved');
      }

      setState(() {
        _avatarFlowState = AvatarOnboardingFlowState.approved;
      });

      if (dialogContext.mounted && Navigator.of(dialogContext).canPop()) {
        Navigator.of(dialogContext).pop();
      }
      await _goToSelfIntroduction();
    } catch (e) {
      debugPrint('avatar approval failed: ${PrivacyLogUtils.errorSummary(e)}');
      if (!mounted) return;
      setState(() {
        _avatarFlowState = AvatarOnboardingFlowState.previewReady;
        _avatarApprovalError = '아바타 저장에 실패했어요. 다시 한 번 선택해주세요.';
      });
      refreshDialog(() {});
    }
  }

  Future<void> _goToSelfIntroduction() async {
    // 원본 사진 URL은 클라이언트가 사용자 문서에 기록하지 않는다.
    // 공개 노출 가능한 값은 승인 시 서버가 쓰는 onboarding.avatarUrls뿐이다.
    final validPhotos = _photos.whereType<String>().toList();

    if (!mounted) return;
    debugPrint(
      'photo upload next -> navigating to: ${RouteNames.onboardingSelfIntro}',
    );

    if (widget.onNext != null) {
      widget.onNext!.call(validPhotos);
    } else {
      Navigator.of(context).pushNamed(RouteNames.onboardingSelfIntro);
    }
  }

  void _showErrorSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  void _failAvatarGeneration(
    String message, {
    required String phase,
    String? jobId,
    Object? error,
  }) {
    _logAvatarFlow(phase, jobId: jobId, error: error);
    if (!mounted) return;
    setState(() {
      _avatarFlowState = AvatarOnboardingFlowState.failed;
      _avatarGenerationError = message;
      if (_activeAvatarJobId != null && _activeAvatarJobId!.isNotEmpty) {
        _avatarSourceLocked = true;
      }
    });
    _showErrorSnack(message);
  }

  void _releaseRejectedSourceSelection() {
    if (!mounted) return;
    setState(() {
      _activeAvatarJobId = null;
      _activeAvatarSourcePhotoId = null;
      _activeSourceSelectionVersion = null;
      _avatarSourceLocked = false;
      _avatarRetryAllowed = false;
      _sourceUploadRequestId = null;
    });
  }

  void _logAvatarFlow(
    String phase, {
    String? jobId,
    String? photoId,
    String? rawStatus,
    AvatarJobStatus? status,
    int? candidateCount,
    int? slotIndex,
    int? sourceSelectionVersion,
    Object? error,
  }) {
    final parts = <String>['[AvatarFlow]', phase];
    if (jobId != null) parts.add('jobId=${_redactIdentifier(jobId)}');
    if (photoId != null) parts.add('photoId=${_redactIdentifier(photoId)}');
    if (rawStatus != null) parts.add('rawStatus=$rawStatus');
    if (status != null) parts.add('status=${status.name}');
    if (candidateCount != null) parts.add('candidateCount=$candidateCount');
    if (slotIndex != null) parts.add('slotIndex=$slotIndex');
    if (sourceSelectionVersion != null) {
      parts.add('sourceSelectionVersion=$sourceSelectionVersion');
    }
    if (error != null) {
      parts.add('error=${PrivacyLogUtils.errorSummary(error)}');
    }
    debugPrint(parts.join(' '));
  }

  String _redactIdentifier(String value) {
    final normalized = value.trim();
    if (normalized.length <= 10) return '<redacted>';
    return '${normalized.substring(0, 10)}...';
  }

  /// 로그에 임시 프리뷰 URL이나 사용자 식별 정보가 새는 것을 방지한다.

  Future<void> _handleBack() async {
    if (_isAvatarFlowActive) {
      final confirmed = await _confirmExitDuringGeneration();
      if (confirmed != true) return;
      _avatarFlowCancelled = true;
      if (_isCandidateDialogOpen && mounted) {
        Navigator.of(context, rootNavigator: false).maybePop();
        _isCandidateDialogOpen = false;
      }
      if (!mounted) return;
      setState(() {
        _avatarFlowState = AvatarOnboardingFlowState.idle;
      });
    }

    if (!mounted) return;

    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  Future<bool?> _confirmExitDuringGeneration() {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) {
        return AlertDialog(
          title: const Text(
            '아바타 생성이 진행 중이에요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontWeight: FontWeight.w700,
            ),
          ),
          content: const Text(
            '지금 나가면 아바타 생성을 중단해요.\n나가시겠어요?',
            style: TextStyle(fontFamily: 'Pretendard'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('계속 기다리기'),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('나가기'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isAvatarFlowActive,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handleBack();
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
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 160),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const _TitleSection(),
                          const SizedBox(height: 24),
                          ProfilePhotoMosaic(
                            gap: 10,
                            featuredBadge: const _FeaturedPhotoBadge(),
                            itemBuilder: (context, index) {
                              return _PhotoSlot(
                                photoUrl: _photos[index],
                                isUploading: _isUploading[index],
                                isLocked:
                                    _avatarLocked &&
                                    _photos[index] == _lockedApprovedAvatarUrl,
                                isDisabled: _isSourceMutationBlocked,
                                onAdd: () => _addPhoto(index),
                                onRemove: () => _removePhoto(index),
                              );
                            },
                          ),
                          const SizedBox(height: 12),
                          const Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(
                                Icons.info_outline_rounded,
                                color: _AppColors.primary,
                                size: 17,
                              ),
                              SizedBox(width: 7),
                              Expanded(
                                child: Text(
                                  '아바타를 생성하는 사진으로, 가입 후 바꿀 수 없어요',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 13,
                                    color: _AppColors.textSub,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          if (_avatarLocked) ...[
                            const SizedBox(height: 16),
                            const Text(
                              lockedAvatarNotice,
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 13,
                                color: _AppColors.textSub,
                                height: 1.4,
                              ),
                            ),
                          ],
                          if (!_avatarLocked &&
                              _hasStartedAvatarSourceLock) ...[
                            const SizedBox(height: 16),
                            const Text(
                              sourceLockedAvatarMessage,
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 13,
                                color: _AppColors.textSub,
                                height: 1.4,
                              ),
                            ),
                          ],
                          const SizedBox(height: 24),
                          _ChatRealPhotoConsentNotice(
                            value: _chatPartnerRealPhotoDisclosure,
                            onChanged: (value) {
                              if (_avatarLocked) {
                                _showLockedAvatarMessage();
                                return;
                              }
                              if (_isSourceMutationBlocked) {
                                _showSourceLockedAvatarMessage();
                                return;
                              }
                              setState(() {
                                _chatPartnerRealPhotoDisclosure = value;
                              });
                            },
                          ),
                          if (_avatarGenerationError != null) ...[
                            const SizedBox(height: 16),
                            AvatarGenerationErrorBanner(
                              message: _avatarGenerationError!,
                              // 서버가 재시도를 허용하지 않은 상태에서는
                              // 재시도를 제안하지 않는다.
                              onRetry: _avatarRetryAllowed
                                  ? _handleAvatarRetry
                                  : null,
                              onStartOver: _avatarAllowsNewGeneration
                                  ? _handleStartOverWithNewPhotos
                                  : null,
                            ),
                          ],
                          const SizedBox(height: 16),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: const [
                              Icon(
                                Icons.info_outline_rounded,
                                color: _AppColors.primary,
                                size: 18,
                              ),
                              SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  '본인이 나오지 않거나 불쾌감을 주는 사진은 통보 없이 삭제될 수 있습니다.',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 12,
                                    color: _AppColors.textSub,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _BottomActionBar(
                  photoCount: _photoCount,
                  minRequired: _minRequiredPhotos,
                  hasApprovedAvatar: _hasApprovedAvatarForProceed,
                  isUploading: _isUploading.any((e) => e),
                  isAvatarGenerating: _isGenerating,
                  onNext: _handleNext,
                ),
              ),
              IgnorePointer(
                ignoring: !_isGenerating,
                child: AvatarGeneratingOverlay(visible: _isGenerating),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    this.onBack,
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
            onPressed: () {
              HapticFeedback.lightImpact();
              if (onBack != null) {
                onBack!.call();
              } else {
                Navigator.of(context).pop();
              }
            },
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

class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: const [
        Text(
          '프로필 사진 등록',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 26,
            fontWeight: FontWeight.bold,
            color: _AppColors.textMain,
            height: 1.3,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '매력을 보여줄 사진을 올려주세요',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.textSub,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '얼굴이 잘 나온 사진일수록 매칭 확률이 올라가요',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

class _ChatRealPhotoConsentNotice extends StatelessWidget {
  final bool value;
  final ValueChanged<bool> onChanged;

  const _ChatRealPhotoConsentNotice({
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _AppColors.borderDashed),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Checkbox(
            value: value,
            activeColor: _AppColors.primary,
            onChanged: (checked) => onChanged(checked == true),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Text(
                  '채팅 상대에게 실제 프로필 사진 공개 동의',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  '추천 화면에는 선택한 아바타가 표시돼요. 채팅방이 만들어진 상대에게는 실제 프로필 사진이 표시될 수 있고, 원본 사진은 추천 카드나 공개 프로필에는 표시되지 않아요.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    color: _AppColors.textSub,
                    height: 1.4,
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

class _PhotoSlot extends StatelessWidget {
  final String? photoUrl;
  final bool isUploading;
  final bool isLocked;
  final bool isDisabled;
  final VoidCallback onAdd;
  final VoidCallback onRemove;

  const _PhotoSlot({
    required this.photoUrl,
    required this.isUploading,
    required this.isLocked,
    required this.isDisabled,
    required this.onAdd,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    if (isUploading) {
      return Container(
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _AppColors.borderDashed),
        ),
        child: const Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(strokeWidth: 2.5),
              ),
              SizedBox(height: 12),
              Text(
                '업로드 중...',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 13,
                  color: _AppColors.textSub,
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (photoUrl != null) {
      final isQueuedSourcePhoto = AvatarSourcePhotoService.isQueuedSlotToken(
        photoUrl,
      );
      return GestureDetector(
        onTap: isLocked ? null : onAdd,
        child: Stack(
          children: [
            Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.black.withValues(alpha: 0.05)),
                image: isQueuedSourcePhoto
                    ? null
                    : DecorationImage(
                        image: NetworkImage(photoUrl!),
                        fit: BoxFit.cover,
                      ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: isQueuedSourcePhoto
                  ? const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.check_circle_rounded,
                            color: _AppColors.primary,
                            size: 32,
                          ),
                          SizedBox(height: 10),
                          Text(
                            'Avatar pending',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 13,
                              color: _AppColors.textSub,
                            ),
                          ),
                        ],
                      ),
                    )
                  : null,
            ),
            if (!isLocked && !isDisabled)
              Positioned(
                top: -8,
                right: -8,
                child: GestureDetector(
                  onTap: onRemove,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: _AppColors.surfaceLight,
                      shape: BoxShape.circle,
                      border: Border.all(color: _AppColors.backgroundLight),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.close_rounded,
                      size: 16,
                      color: _AppColors.textGray,
                    ),
                  ),
                ),
              ),
            if (isLocked)
              Positioned(
                right: 8,
                bottom: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.lock_rounded, size: 12, color: Colors.white),
                      SizedBox(width: 4),
                      Text(
                        '잠김',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 11,
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      );
    }

    return GestureDetector(
      onTap: isLocked ? null : onAdd,
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _AppColors.borderDashed,
            width: 2,
            style: BorderStyle.none,
          ),
        ),
        child: CustomPaint(
          painter: _DashedBorderPainter(
            color: _AppColors.borderDashed,
            strokeWidth: 2,
            gap: 4,
          ),
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: _AppColors.backgroundLight,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.add_rounded,
                    color: _AppColors.textGray,
                    size: 24,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  '추가',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textSub,
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

class _FeaturedPhotoBadge extends StatelessWidget {
  const _FeaturedPhotoBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: _AppColors.primary,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 2,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: const Text(
        '대표 사진',
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
      ),
    );
  }
}

class _DashedBorderPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  final double gap;

  _DashedBorderPainter({
    required this.color,
    this.strokeWidth = 2,
    this.gap = 4,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final Paint paint = Paint()
      ..color = color
      ..strokeWidth = strokeWidth
      ..style = PaintingStyle.stroke;

    final Path path = Path()
      ..addRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(0, 0, size.width, size.height),
          const Radius.circular(16),
        ),
      );

    final Path dashPath = Path();
    final double dashWidth = 8.0;

    for (final metric in path.computeMetrics()) {
      double distance = 0.0;
      while (distance < metric.length) {
        dashPath.addPath(
          metric.extractPath(distance, distance + dashWidth),
          Offset.zero,
        );
        distance += dashWidth + gap;
      }
    }

    canvas.drawPath(dashPath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _BottomActionBar extends StatelessWidget {
  final int photoCount;
  final int minRequired;
  final bool hasApprovedAvatar;
  final bool isUploading;
  final bool isAvatarGenerating;
  final Future<void> Function() onNext;

  const _BottomActionBar({
    required this.photoCount,
    required this.minRequired,
    required this.hasApprovedAvatar,
    required this.isUploading,
    required this.isAvatarGenerating,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final bool canProceed =
        (photoCount >= minRequired || hasApprovedAvatar) &&
        !isUploading &&
        !isAvatarGenerating;
    final String label = isAvatarGenerating
        ? '아바타 생성중...'
        : (isUploading ? '업로드 중...' : '다음');

    return Container(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 14,
            offset: const Offset(0, -4),
          ),
        ],
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Text(
                  '$photoCount / 6장',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.textSub,
                  ),
                ),
                const Spacer(),
                Text(
                  '최소 $minRequired장 필요',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    color: _AppColors.textGray,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              height: 54,
              child: ElevatedButton(
                onPressed: canProceed ? onNext : null,
                style: ElevatedButton.styleFrom(
                  elevation: 0,
                  backgroundColor: canProceed
                      ? _AppColors.primary
                      : _AppColors.primary.withValues(alpha: 0.35),
                  disabledBackgroundColor: _AppColors.primary.withValues(
                    alpha: 0.35,
                  ),
                  foregroundColor: Colors.white,
                  disabledForegroundColor: Colors.white.withValues(alpha: 0.7),
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
            ),
          ],
        ),
      ),
    );
  }
}
