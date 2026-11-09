import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

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
import '../services/avatar_generation_session_controller.dart';
import '../services/avatar_resume_policy.dart';
import '../services/avatar_upload_submission_guard.dart';
import '../widgets/avatar_generation_error_banner.dart';
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

/// 온보딩 사진 등록 화면.
///
/// "다음" 은 source-set admission(`beginFromOnboardingPhotos`) 만 하고 jobId 를
/// [AvatarGenerationSessionController] 에 넘긴 뒤 즉시 다음 단계로 넘어간다.
/// 생성 대기·후보 선택·승인은 이 화면에서 하지 않는다. 마지막(아바타 선택)
/// 화면이 컨트롤러 상태로 처리한다. admission 자체 실패와 재진입 시 서버가
/// 알려준 실패 상태만 이 화면에서 다룬다.
class PhotoUploadScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final Function(List<String> photos)? onNext;

  /// 아바타 생성 admission 을 담당하는 클라이언트. 기본값은 백엔드 콜러블을
  /// 호출하는 [BackendAvatarGenerationClient]이며, 위젯 테스트/디자인 QA에서만
  /// [MockAvatarGenerationClient]를 주입해 사용합니다.
  final AvatarGenerationClient? avatarGenerationClient;
  final OnboardingPhotoUploadService? onboardingPhotoUploadService;

  /// 테스트 주입용 세션 컨트롤러. 없으면 앱 루트 Provider 에서 찾고, 그것도
  /// 없으면(단독 위젯 테스트) 컨트롤러 없이 진행한다.
  final AvatarGenerationSessionController? avatarSessionController;

  /// Test-only initial slot values for exercising the admission flow without
  /// invoking the image picker or Firebase upload.
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
    this.avatarSessionController,
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
  AvatarGenerationSessionController? _sessionController;
  bool _sessionControllerResolved = false;
  AvatarOnboardingFlowState _avatarFlowState = AvatarOnboardingFlowState.idle;
  String? _avatarGenerationError;
  bool _chatPartnerRealPhotoDisclosure = false;
  bool _avatarLocked = false;
  bool _avatarSourceLocked = false;
  String _lockedApprovedAvatarUrl = '';
  String? _activeAvatarJobId;
  bool _avatarRetryAllowed = true;
  // needs_review / 최종 실패에서 "사진을 바꾸고 다시 만들기"를 허용하는가.
  // 재시도와 다른 축이며, provider 결과 미확인 상태에서는 둘 다 false 다.
  bool _avatarAllowsNewGeneration = false;

  int get _photoCount => _photos.where((p) => p != null).length;

  // 사진 최소 장수는 production 계약이며 빌드 플래그로 완화할 수 없다.
  int get _minRequiredPhotos => _requiredPhotoCount;

  // 승인된 아바타 보유 여부는 서버 프로필에서 파생된 잠금 상태만 신뢰한다.
  // 슬롯 문자열 검사로 판정하면 일반 사진 URL이 승인으로 오인된다.
  bool get _hasApprovedAvatarForProceed => _avatarLocked;

  /// admission 콜러블이 진행 중이다. 이 동안만 "다음" 을 막는다.
  bool get _isSubmitting =>
      _avatarFlowState == AvatarOnboardingFlowState.uploadingSourcePhoto;

  bool get _hasStartedAvatarSourceLock =>
      _avatarSourceLocked ||
      (_activeAvatarJobId != null && _activeAvatarJobId!.isNotEmpty);

  bool get _isSourceMutationBlocked =>
      _avatarLocked ||
      _hasStartedAvatarSourceLock ||
      _isSubmitting ||
      _isUploading.any((value) => value);

  AuthService get _auth => _authService ??= AuthService();

  OnboardingPhotoUploadService get _onboardingPhotoService =>
      _onboardingPhotoUploadService ??=
          widget.onboardingPhotoUploadService ?? OnboardingPhotoUploadService();

  StorageService get _storage => _storageService ??= StorageService();

  UserService get _users => _userService ??= UserService();

  /// 세션 컨트롤러. 위젯 주입 → Provider → 없음 순으로 한 번만 해석한다.
  AvatarGenerationSessionController? get _session {
    if (_sessionControllerResolved) return _sessionController;
    _sessionControllerResolved = true;
    final injected = widget.avatarSessionController;
    if (injected != null) return _sessionController = injected;
    try {
      return _sessionController = context
          .read<AvatarGenerationSessionController>();
    } on ProviderNotFoundException {
      return _sessionController = null;
    }
  }

  @override
  void initState() {
    super.initState();
    _avatarClient =
        widget.avatarGenerationClient ?? BackendAvatarGenerationClient();
    _prewarmAvatarWorkerIfNeeded();
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

  Future<void> _loadExistingPhotos() async {
    final kakaoUserId = await _storage.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final data = await _users.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;

    final profile = Map<String, dynamic>.from(data);
    final lockState = avatarLockStateFromUserProfile(profile);
    final sourceLocked = avatarSourceLockedFromUserProfile(profile);
    final sourceJobId = avatarSourceJobIdFromUserProfile(profile);
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
  /// 생긴다. 진행 중인 작업이 있으면 잠금만 걸고 "다음" 은 그대로 통과시킨다.
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
          _avatarFlowState = AvatarOnboardingFlowState.idle;
        });
        // 세션 컨트롤러가 진행을 지켜본다(배너/마지막 화면).
        unawaited(_session?.adoptJob(plan.jobId));
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

  /// 재시도 버튼 진입점. 한 프레임 안에 두 번 눌려도 서버 호출이 두 번 나가지
  /// 않도록 "다음" 버튼과 동일한 재진입 가드를 공유한다.
  ///
  /// 재시도 가능 여부의 권위는 서버다. 서버가 허용한 실패는 서버 재시도
  /// 콜러블(같은 logical generation 재디스패치)을 거치고, 서버가 거부하면
  /// 재시도 없이 그 이유를 보여준다. 재시도 뒤에는 잠금 상태로 이 화면에 머물고
  /// 사용자가 "다음" 으로 이어간다.
  Future<void> _handleAvatarRetry() async {
    // 상태 가드: 재시도가 이미 소진/거부된 뒤 같은 프레임의 stale 버튼 탭을 막는다.
    if (!_avatarRetryAllowed) return;
    if (_isSubmitting || _isHandlingNext) return;
    _isHandlingNext = true;
    try {
      final jobId = _findPrimaryAvatarJobId();
      final snapshot = await _avatarClient.getCurrentGenerationStatus();
      if (!mounted) return;
      final plan = planAvatarResume(snapshot);
      if (plan.action == AvatarResumeAction.showRetryable &&
          plan.retryAllowed) {
        final retried = await _avatarClient.retryCurrentGeneration(
          clientRequestId: AvatarSourcePhotoService.createClientRequestId(),
        );
        if (!mounted) return;
        final retriedJobId = retried?.jobId ?? '';
        setState(() {
          if (retriedJobId.isNotEmpty) _activeAvatarJobId = retriedJobId;
          _avatarSourceLocked = true;
          _avatarGenerationError = null;
          _avatarAllowsNewGeneration = false;
          _avatarFlowState = AvatarOnboardingFlowState.idle;
        });
        final adoptedJobId = _findPrimaryAvatarJobId();
        if (adoptedJobId != null) {
          unawaited(_session?.adoptJob(adoptedJobId));
        }
        _logAvatarFlow('avatar_retry_dispatched', jobId: adoptedJobId);
        return;
      }
      if (plan.action == AvatarResumeAction.resumeGenerating ||
          plan.action == AvatarResumeAction.resumePreview) {
        // 서버는 이미 진행 중이다. 실패 배너를 걷고 잠금 상태로 둔다.
        setState(() {
          if (plan.jobId.isNotEmpty) _activeAvatarJobId = plan.jobId;
          _avatarSourceLocked = true;
          _avatarGenerationError = null;
          _avatarFlowState = AvatarOnboardingFlowState.idle;
        });
        if (plan.jobId.isNotEmpty) unawaited(_session?.adoptJob(plan.jobId));
        return;
      }
      if (plan.action == AvatarResumeAction.showTerminal ||
          plan.action == AvatarResumeAction.showNeedsReview ||
          plan.action == AvatarResumeAction.showReconciliation ||
          plan.action == AvatarResumeAction.showRetryable) {
        _avatarRetryAllowed = plan.retryAllowed;
        _avatarAllowsNewGeneration = plan.allowsNewGeneration;
        _failAvatarGeneration(
          plan.message,
          phase: 'avatar_retry_refused_by_server',
          jobId: jobId,
        );
        return;
      }
      if (plan.action == AvatarResumeAction.resumeApproved) {
        setState(() {
          _avatarLocked = true;
          _avatarGenerationError = null;
          _avatarFlowState = AvatarOnboardingFlowState.approved;
        });
        return;
      }
      // 서버 상태를 읽지 못했거나 작업이 없다. 안내만 남긴다.
      _avatarRetryAllowed = plan.action == AvatarResumeAction.unavailable;
      _failAvatarGeneration(
        avatarGenerationDelayedMessage,
        phase: 'avatar_retry_status_unavailable',
        jobId: jobId,
      );
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
    if (_isSubmitting || _isHandlingNext) return;
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
      _session?.reset();
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
        });
      }

      // P1-9: bounded pick — the picker downsizes huge frames before they
      // are read into memory, so the UI stays responsive and the callable
      // payload stays small. The server re-validates the bound.
      final XFile? pickedFile = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        maxWidth: OnboardingPhotoUploadService.maxPickDimension.toDouble(),
        maxHeight: OnboardingPhotoUploadService.maxPickDimension.toDouble(),
        imageQuality: OnboardingPhotoUploadService.pickImageQuality,
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
    if (_isSubmitting || _isHandlingNext) {
      return;
    }
    _isHandlingNext = true;
    try {
      if (!_hasApprovedAvatarForProceed &&
          !_hasStartedAvatarSourceLock &&
          _photoCount < _minRequiredPhotos) {
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
        // 이미 승인된 아바타가 있는 재방문 사용자는 생성 없이 진행한다.
        await _goToSelfIntroduction();
        return;
      }

      final existingJobId = _findPrimaryAvatarJobId();
      if (existingJobId != null) {
        // 서버가 이미 생성을 받아들였다(재진입/뒤로가기). 다시 admission 하지
        // 않고 세션 컨트롤러에 맡긴 채 다음 단계로 넘어간다.
        unawaited(_session?.adoptJob(existingJobId));
        await _goToSelfIntroduction();
        return;
      }
      if (_hasStartedAvatarSourceLock) {
        // 잠겨 있는데 jobId 를 모른다. 서버 상태로 복구를 시도한다.
        await _resumeFromServerStatus();
        if (!mounted) return;
        final resumedJobId = _findPrimaryAvatarJobId();
        if (resumedJobId != null) {
          unawaited(_session?.adoptJob(resumedJobId));
          await _goToSelfIntroduction();
          return;
        }
        if (_avatarFlowState != AvatarOnboardingFlowState.failed) {
          _failAvatarGeneration(
            sourceLockedAvatarFailureMessage,
            phase: 'avatar_source_locked_missing_job',
          );
        }
        return;
      }

      final jobId = await _beginAvatarGenerationFromUploadedPhotos();
      if (jobId == null || !mounted) return;
      // 대기하지 않는다. 생성 진행은 세션 컨트롤러가 지켜보고, 후보 선택은
      // 온보딩 마지막 화면에서 한다.
      unawaited(_session?.adoptJob(jobId));
      await _goToSelfIntroduction();
    } finally {
      _isHandlingNext = false;
    }
  }

  /// 사진을 고르는 동안 워커를 미리 깨운다(best effort, Azure 호출 없음).
  /// 이미 승인된 아바타로 잠긴 화면은 새 생성이 없으므로 건너뛴다.
  void _prewarmAvatarWorkerIfNeeded() {
    final lockedUrl = widget.lockedApprovedAvatarUrlForTesting?.trim() ?? '';
    if (lockedUrl.isNotEmpty) return;
    unawaited(
      _avatarClient.prewarmWorker().catchError((Object error) {
        // Best effort: a warmup failure must never reach the photo flow.
        debugPrint(
          'avatar worker prewarm failed: ${PrivacyLogUtils.errorSummary(error)}',
        );
      }),
    );
  }

  String? _findPrimaryAvatarJobId() {
    final jobId = _activeAvatarJobId;
    return jobId == null || jobId.isEmpty ? null : jobId;
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
        _avatarSourceLocked = true;
        _avatarRetryAllowed = true;
        _avatarAllowsNewGeneration = false;
        _avatarFlowState = AvatarOnboardingFlowState.idle;
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
      // 다른 기기/이전 세션이 이미 admission 했다. 서버 lock 을 그대로 받아
      // 활성 job 으로 이어간다.
      await _loadExistingPhotos();
      if (!mounted) return null;
      final resumedJobId = _findPrimaryAvatarJobId();
      if (resumedJobId != null) {
        setState(() => _avatarFlowState = AvatarOnboardingFlowState.idle);
        return resumedJobId;
      }
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
    // admission 콜러블이 나가는 짧은 순간에는 뒤로가기를 무시한다. 생성 자체는
    // 서버에서 이어지므로 확인 다이얼로그는 필요 없다.
    if (_isSubmitting) return;
    if (!mounted) return;

    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isSubmitting,
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
                  hasActiveGeneration: _hasStartedAvatarSourceLock,
                  isUploading: _isUploading.any((e) => e),
                  isSubmitting: _isSubmitting,
                  onNext: _handleNext,
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

  /// 서버가 이미 생성을 받아들였다(활성 job / source lock). 슬롯에는 합성
  /// 토큰 하나만 남아 있을 수 있으므로 장수와 무관하게 "다음" 을 허용한다.
  final bool hasActiveGeneration;
  final bool isUploading;

  /// admission 콜러블이 나가는 중. 이때만 "다음" 을 잠깐 막는다.
  final bool isSubmitting;
  final Future<void> Function() onNext;

  const _BottomActionBar({
    required this.photoCount,
    required this.minRequired,
    required this.hasApprovedAvatar,
    required this.hasActiveGeneration,
    required this.isUploading,
    required this.isSubmitting,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final bool canProceed =
        (photoCount >= minRequired ||
            hasApprovedAvatar ||
            hasActiveGeneration) &&
        !isUploading &&
        !isSubmitting;
    final String label = isSubmitting
        ? '아바타 생성 준비 중...'
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
