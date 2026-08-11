import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/avatar_generation_client.dart';
import '../../../services/avatar_source_photo_service.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/utils/avatar_lock_policy.dart';
import '../../../shared/utils/privacy_log_utils.dart';
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

  /// ?꾨컮? ?앹꽦/?뱀씤 ?먮쫫???대떦?섎뒗 ?대씪?댁뼵?? 湲곕낯媛믪? 諛깆뿏??肄쒕윭釉붿쓣
  /// ?몄텧?섎뒗 [BackendAvatarGenerationClient]?대ŉ, ?꾩젽 ?뚯뒪???붿옄??QA?먯꽌留?  /// [MockAvatarGenerationClient]瑜?二쇱엯???ъ슜?⑸땲??
  final AvatarGenerationClient? avatarGenerationClient;

  /// Test-only initial slot values for exercising the avatar polling and
  /// approval flow without invoking the image picker or Firebase upload.
  final List<String?>? initialPhotosForTesting;

  const PhotoUploadScreen({
    super.key,
    this.currentStep = 5,
    this.totalSteps = 8,
    this.onBack,
    this.onNext,
    this.avatarGenerationClient,
    this.initialPhotosForTesting,
  });

  @override
  State<PhotoUploadScreen> createState() => _PhotoUploadScreenState();
}

class _PhotoUploadScreenState extends State<PhotoUploadScreen> {
  static const int _minRequiredPhotos = 2;
  static const Duration _avatarPollInterval = Duration(seconds: 2);
  static const Duration _avatarPollTimeout = Duration(seconds: 300);

  final ImagePicker _imagePicker = ImagePicker();

  final List<String?> _photos = List<String?>.filled(6, null);
  final List<bool> _isUploading = List<bool>.filled(6, false);

  AuthService? _authService;
  AvatarSourcePhotoService? _avatarSourcePhotoService;
  StorageService? _storageService;
  UserService? _userService;
  bool _isSavingOnExit = false;

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

  int get _photoCount => _photos.where((p) => p != null).length;

  bool get _hasApprovedAvatarForProceed =>
      _avatarLocked ||
      _photos.any(
        (value) =>
            value != null &&
            value.isNotEmpty &&
            AvatarSourcePhotoService.queuedJobId(value) == null,
      );

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

  AvatarSourcePhotoService get _sourcePhotoService =>
      _avatarSourcePhotoService ??= AvatarSourcePhotoService();

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
      final firstSafeApproved = initialPhotos.whereType<String>().firstWhere(
        (value) =>
            AvatarSourcePhotoService.queuedJobId(value) == null &&
            isSafePublicApprovedAvatarUrl(value),
        orElse: () => '',
      );
      _avatarLocked = firstSafeApproved.isNotEmpty;
      _lockedApprovedAvatarUrl = firstSafeApproved;
      for (final value in initialPhotos.whereType<String>()) {
        final queuedJobId = AvatarSourcePhotoService.queuedJobId(value);
        if (queuedJobId != null && queuedJobId.isNotEmpty) {
          _activeAvatarJobId = queuedJobId;
          _avatarSourceLocked = true;
        }
      }
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
  }

  Future<void> _addPhoto(int index) async {
    HapticFeedback.lightImpact();
    if (_avatarLocked) {
      _showLockedAvatarMessage();
      return;
    }
    if (_isSourceMutationBlocked) {
      _showSourceLockedAvatarMessage();
      return;
    }

    try {
      final XFile? pickedFile = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 88,
      );

      if (pickedFile == null) {
        return;
      }

      setState(() {
        final replacedJobId = AvatarSourcePhotoService.queuedJobId(
          _photos[index],
        );
        if (replacedJobId != null && replacedJobId == _activeAvatarJobId) {
          _activeAvatarJobId = null;
          _activeAvatarSourcePhotoId = null;
          _activeSourceSelectionVersion = null;
        }
        _isUploading[index] = true;
        _avatarFlowCancelled = true;
      });

      final String? kakaoUserId = await _storage.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('?ъ슜???뺣낫瑜?李얠쓣 ???놁뒿?덈떎. ?ㅼ떆 濡쒓렇?명빐二쇱꽭??');
      }

      final hasFirebaseSession = await _auth
          .ensureFirebaseSessionForVerifiedUser(kakaoUserId);
      if (!hasFirebaseSession) {
        throw Exception(
          'Firebase login session is required for private upload.',
        );
      }

      _logAvatarFlow('avatar_upload_start', slotIndex: index);
      final result = await _sourcePhotoService.uploadPickedImage(
        file: pickedFile,
        slotIndex: index,
        uid: kakaoUserId,
        chatPartnerRealPhotoDisclosure: _chatPartnerRealPhotoDisclosure,
      );
      _logAvatarFlow(
        'avatar_upload_success',
        jobId: result.jobId,
        photoId: result.photoId,
        rawStatus: result.avatarStatus,
        sourceSelectionVersion: result.sourceSelectionVersion,
      );

      if (!mounted) return;

      setState(() {
        _photos[index] = AvatarSourcePhotoService.queuedSlotToken(result.jobId);
        _activeAvatarJobId = result.jobId;
        _activeAvatarSourcePhotoId = result.photoId;
        _activeSourceSelectionVersion = result.sourceSelectionVersion;
        _avatarSourceLocked = true;
        _avatarFlowCancelled = false;
        _isUploading[index] = false;
        _avatarGenerationError = null;
      });
    } catch (e) {
      _logAvatarFlow('avatar_upload_failed', slotIndex: index, error: e);
      if (!mounted) return;

      setState(() {
        _isUploading[index] = false;
        if (e is AvatarSourceLockedException) {
          _avatarSourceLocked = true;
          _avatarFlowCancelled = false;
        }
      });
      if (e is! AvatarSourceLockedException) {
        await _loadExistingPhotos();
        if (!mounted) return;
      }

      final lockMessage = e is AvatarAlreadyApprovedException
          ? AvatarAlreadyApprovedException.message
          : e is AvatarSourceLockedException
          ? AvatarSourceLockedException.message
          : null;
      if (lockMessage != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(lockMessage),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('?ъ쭊 ?낅줈?쒖뿉 ?ㅽ뙣?덉뼱?? ?좎떆 ???ㅼ떆 ?쒕룄?댁＜?몄슂.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
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
    if (_isAvatarFlowActive) {
      return;
    }

    if (_photoCount < _minRequiredPhotos && !_hasApprovedAvatarForProceed) {
      HapticFeedback.heavyImpact();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('?ъ쭊??理쒖냼 2???댁긽 ?깅줉?댁＜?몄슂.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    if (_isUploading.any((e) => e)) {
      HapticFeedback.heavyImpact();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('?ъ쭊 ?낅줈?쒓? ?앸궃 ???ㅼ쓬?쇰줈 ?섏뼱媛二쇱꽭??'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    HapticFeedback.mediumImpact();
    await _startAvatarGeneration();
  }

  String? _findPrimaryAvatarJobId() {
    final jobId = _activeAvatarJobId;
    return jobId == null || jobId.isEmpty ? null : jobId;
  }

  Future<void> _startAvatarGeneration() async {
    final jobId = _findPrimaryAvatarJobId();
    if (jobId == null) {
      if (_hasStartedAvatarSourceLock) {
        _failAvatarGeneration(
          sourceLockedAvatarFailureMessage,
          phase: 'avatar_source_locked_missing_job',
        );
        return;
      }
      // ?먯엵?????꾨컮? ?묒뾽???놁쑝硫??대? ?뱀씤???꾨컮?媛 ?덈떎怨?蹂닿퀬
      // ?ㅼ쓬 ?④퀎濡??대룞?쒕떎. 諛깆뿏?쒓? onboarding.avatarUrls???뱀씤??URL留?      // 湲곕줉?섎?濡???寃쎈줈???щ갑臾??대? ?뱀씤 ?꾨즺) ?쒕굹由ъ삤???대떦?쒕떎.
      await _goToSelfIntroduction();
      return;
    }

    if (!mounted) return;
    setState(() {
      _avatarFlowCancelled = false;
      _avatarGenerationError = null;
      _avatarApprovalError = null;
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
        _failAvatarGeneration(
          avatarGenerationFailureMessage(
            status: result.status,
            errorCode: result.errorCode,
          ),
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
      // ?꾩젽??dispose?섍굅???ъ슜?먭? 紐낆떆?곸쑝濡??먮쫫??以묐떒??寃쎌슦.
    } on TimeoutException {
      if (!mounted) return;
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
        _avatarApprovalError = '?꾨컮? ??μ뿉 ?ㅽ뙣?덉뼱?? ?ㅼ떆 ??踰??좏깮?댁＜?몄슂.';
      });
      refreshDialog(() {});
    }
  }

  Future<void> _goToSelfIntroduction() async {
    final validPhotos = _photos.whereType<String>().toList();
    if (!_avatarLocked) {
      try {
        await OnboardingSaveHelper.savePhotos(validPhotos);
      } catch (e) {
        debugPrint(
          'avatar onboarding savePhotos failed: ${PrivacyLogUtils.errorSummary(e)}',
        );
      }
    }

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

  /// 濡쒓렇???꾩떆 ?꾨━酉?URL?대굹 ?ъ슜???앸퀎 ?뺣낫媛 ?덈뒗 寃껋쓣 諛⑹??쒕떎.

  Future<void> _saveCurrentPhotos() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;

    try {
      final validPhotos = _photos.whereType<String>().toList();
      if (!_avatarLocked) {
        await OnboardingSaveHelper.savePhotos(validPhotos);
      }
    } finally {
      _isSavingOnExit = false;
    }
  }

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

    await _saveCurrentPhotos();
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
            '?꾨컮? ?앹꽦??吏꾪뻾 以묒씠?먯슂',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontWeight: FontWeight.w700,
            ),
          ),
          content: const Text(
            '吏湲??섍?硫??꾨컮? ?앹꽦??以묐떒?댁슂.\n?섍??쒓쿋?댁슂?',
            style: TextStyle(fontFamily: 'Pretendard'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('怨꾩냽 湲곕떎由ш린'),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('?섍?湲?),
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
                          GridView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            gridDelegate:
                                const SliverGridDelegateWithFixedCrossAxisCount(
                                  crossAxisCount: 2,
                                  childAspectRatio: 3 / 4,
                                  crossAxisSpacing: 12,
                                  mainAxisSpacing: 12,
                                ),
                            itemCount: 6,
                            itemBuilder: (context, index) {
                              return _PhotoSlot(
                                index: index,
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
                              onRetry: _startAvatarGeneration,
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
                                  '蹂몄씤???섏삤吏 ?딄굅??遺덉풄媛먯쓣 二쇰뒗 ?ъ쭊? ?듬낫 ?놁씠 ??젣?????덉뒿?덈떎.',
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
          '?꾨줈???ъ쭊 ?깅줉',
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
          '留ㅻ젰??蹂댁뿬以??ъ쭊???щ젮二쇱꽭??,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.textSub,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '?쇨뎬?????섏삩 ?ъ쭊?쇱닔濡?留ㅼ묶 ?뺣쪧???щ씪媛??,
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
                  '梨꾪똿 ?곷??먭쾶 ?ㅼ젣 ?꾨줈???ъ쭊 怨듦컻 ?숈쓽',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  '異붿쿇 ?붾㈃?먮뒗 ?좏깮???꾨컮?媛 ?쒖떆?쇱슂. 梨꾪똿諛⑹씠 留뚮뱾?댁쭊 ?곷??먭쾶???ㅼ젣 ?꾨줈???ъ쭊???쒖떆?????덇퀬, ?먮낯 ?ъ쭊? 異붿쿇 移대뱶??怨듦컻 ?꾨줈?꾩뿉???쒖떆?섏? ?딆븘??',
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
  final int index;
  final String? photoUrl;
  final bool isUploading;
  final bool isLocked;
  final bool isDisabled;
  final VoidCallback onAdd;
  final VoidCallback onRemove;

  const _PhotoSlot({
    required this.index,
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
                '?낅줈??以?..',
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
            if (index == 0)
              Positioned(
                top: 8,
                left: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
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
                    '???,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
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
                        '?좉?',
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
                  '異붽?',
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
        ? '?꾨컮? ?앹꽦以?..'
        : (isUploading ? '?낅줈??以?..' : '?ㅼ쓬');

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
                  '$photoCount / 6??,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.textSub,
                  ),
                ),
                const Spacer(),
                Text(
                  '理쒖냼 $minRequired???꾩슂',
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
