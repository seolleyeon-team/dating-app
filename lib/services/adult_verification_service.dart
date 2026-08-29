import 'package:flutter/foundation.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:uuid/uuid.dart';

import '../config/portone_config.dart';
import 'adult_verification_result.dart';
import 'storage_service.dart';

class AdultVerificationConfig {
  const AdultVerificationConfig({
    required this.storeId,
    required this.channelKey,
    required this.provider,
  });

  static const fromEnvironment = AdultVerificationConfig(
    storeId: PortOneConfig.storeId,
    channelKey: PortOneConfig.kgInicisIdentityChannelKey,
    provider: PortOneConfig.verificationProvider,
  );

  final String storeId;
  final String channelKey;
  final String provider;

  bool get isPortOneConfigured =>
      storeId.trim().isNotEmpty && channelKey.trim().isNotEmpty;
}

class AdultVerificationService {
  AdultVerificationService({
    StorageService? storageService,
    FirebaseFunctions? functions,
  }) : _storageService = storageService ?? StorageService(),
       _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  static const String providerPortOneKgInicis =
      PortOneConfig.verificationProvider;
  static const String providerMock = 'mock_debug';

  /// Production builds must verify through PortOne before Kakao login.
  /// This flag exists only for an explicitly opted-in local debug build.
  static const bool isTemporarilyDisabled = bool.fromEnvironment(
    'ADULT_VERIFICATION_BYPASS',
    defaultValue: false,
  );

  final StorageService _storageService;
  final FirebaseFunctions _functions;
  final Uuid _uuid = const Uuid();

  bool get canUseMockVerification =>
      kDebugMode && PortOneConfig.showDevAdultVerificationControls;

  Future<AdultVerificationResult> getPendingSession() async {
    return await _storageService.getPendingAdultVerificationResult() ??
        AdultVerificationResult.notStarted;
  }

  Future<bool> hasVerifiedServerResult() async {
    if (isTemporarilyDisabled) return true;

    final result = await getPendingSession();
    return result.isVerified;
  }

  Future<bool> hasPendingKakaoLoginSession() async {
    if (isTemporarilyDisabled) return true;

    final result = await getPendingSession();
    if (result.isExpired) {
      await clearPendingSession();
      return false;
    }
    return result.canProceedToKakao;
  }

  Future<void> clearPendingSession() async {
    await _storageService.clearPendingAdultVerificationResult();
  }

  String createIdentityVerificationId() {
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch;
    final random = _uuid.v4().split('-').first;
    return 'seolleyen-preauth-$timestamp-$random';
  }

  Future<AdultVerificationResult> startVerification({
    AdultVerificationConfig config = AdultVerificationConfig.fromEnvironment,
  }) async {
    final identityVerificationId = createIdentityVerificationId();
    final inProgress = AdultVerificationResult(
      status: AdultVerificationStatus.inProgress,
      sessionId: identityVerificationId,
      provider: config.provider,
    );
    await _storageService.savePendingAdultVerificationResult(inProgress);
    return inProgress;
  }

  Future<AdultVerificationResult> savePortOneSuccess({
    required String identityVerificationId,
    required String identityVerificationTxId,
    String provider = providerPortOneKgInicis,
    Map<String, dynamic> providerPayload = const <String, dynamic>{},
  }) async {
    final now = DateTime.now().toUtc();
    final result = AdultVerificationResult(
      status: AdultVerificationStatus.pendingKakaoLogin,
      sessionId: identityVerificationId,
      identityVerificationTxId: identityVerificationTxId,
      provider: provider,
      verifiedAt: now,
      expiresAt: now.add(
        const Duration(minutes: PortOneConfig.pendingSessionMinutes),
      ),
      message: '본인인증이 완료되었어요. 이제 카카오 로그인을 진행해 주세요.',
      providerPayload: providerPayload,
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  Future<AdultVerificationResult> saveFailure({
    required AdultVerificationStatus status,
    String? identityVerificationId,
    String? identityVerificationTxId,
    String? message,
    String provider = providerPortOneKgInicis,
    Map<String, dynamic> providerPayload = const <String, dynamic>{},
  }) async {
    final result = AdultVerificationResult(
      status: status,
      sessionId: identityVerificationId,
      identityVerificationTxId: identityVerificationTxId,
      provider: provider,
      message: message,
      providerPayload: providerPayload,
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  Future<AdultVerificationResult> markServerVerificationInProgress() async {
    final current = await getPendingSession();
    final updated = current.copyWith(
      status: AdultVerificationStatus.pendingServerVerification,
      message: '본인인증 결과를 서버에서 확인하고 있어요.',
    );
    await _storageService.savePendingAdultVerificationResult(updated);
    return updated;
  }

  Future<AdultVerificationResult> verifyPendingSessionAfterLogin() async {
    if (isTemporarilyDisabled) {
      return AdultVerificationResult(
        status: AdultVerificationStatus.verified,
        provider: providerMock,
        verifiedAt: DateTime.now().toUtc(),
        message: '본인인증 절차가 임시 비활성화되어 있어요.',
        providerPayload: const {'temporaryBypass': true},
      );
    }

    final pending = await getPendingSession();
    if (!pending.canProceedToKakao) {
      final failed = AdultVerificationResult(
        status: AdultVerificationStatus.failed,
        provider: providerPortOneKgInicis,
        message: pending.isExpired
            ? '본인인증 세션이 만료되었어요. 다시 인증해 주세요.'
            : '본인인증을 먼저 완료해 주세요.',
      );
      await _storageService.savePendingAdultVerificationResult(failed);
      return failed;
    }

    await markServerVerificationInProgress();
    try {
      final callable = _functions.httpsCallable(
        'verifyAdultIdentityAfterLogin',
      );
      final response = await callable.call(<String, dynamic>{
        'identityVerificationId': pending.sessionId,
        'identityVerificationTxId': pending.identityVerificationTxId,
      });
      final data = Map<String, dynamic>.from(
        (response.data as Map?)?.cast<String, dynamic>() ?? const {},
      );
      final status = data['status']?.toString();

      if (status == 'adult_verified' || data['adultVerified'] == true) {
        final verified = pending.copyWith(
          status: AdultVerificationStatus.verified,
          message: '서버 검증이 완료되었어요.',
        );
        await clearPendingSession();
        return verified;
      }

      if (status == 'adult_verification_under_age') {
        final underAge = pending.copyWith(
          status: AdultVerificationStatus.underAge,
          message: '설레연은 연 나이 20세 이상만 이용할 수 있어요.',
        );
        await _storageService.savePendingAdultVerificationResult(underAge);
        return underAge;
      }

      final failed = pending.copyWith(
        status: AdultVerificationStatus.failed,
        message:
            data['message']?.toString() ?? '서버 본인인증 검증이 완료되지 않았어요. 다시 인증해 주세요.',
      );
      await _storageService.savePendingAdultVerificationResult(failed);
      return failed;
    } on FirebaseFunctionsException catch (e) {
      final code = e.code.toLowerCase();
      final failedStatus = code.contains('permission-denied')
          ? AdultVerificationStatus.underAge
          : AdultVerificationStatus.failed;
      final failed = pending.copyWith(
        status: failedStatus,
        message:
            e.message ??
            (failedStatus == AdultVerificationStatus.underAge
                ? '설레연은 연 나이 20세 이상만 이용할 수 있어요.'
                : '서버 본인인증 검증에 실패했어요. 다시 인증해 주세요.'),
      );
      await _storageService.savePendingAdultVerificationResult(failed);
      return failed;
    } catch (e) {
      final failed = pending.copyWith(
        status: AdultVerificationStatus.failed,
        message: '서버 본인인증 검증에 실패했어요. 다시 인증해 주세요.',
      );
      await _storageService.savePendingAdultVerificationResult(failed);
      return failed;
    }
  }

  Future<AdultVerificationResult> verifyWithPortOne({
    AdultVerificationConfig config = AdultVerificationConfig.fromEnvironment,
    String? sessionId,
  }) async {
    final identityVerificationId = sessionId ?? createIdentityVerificationId();

    if (!config.isPortOneConfigured) {
      final result = AdultVerificationResult(
        status: AdultVerificationStatus.failed,
        sessionId: identityVerificationId,
        provider: providerPortOneKgInicis,
        message: '포트원 본인인증 설정이 아직 등록되지 않았어요.',
      );
      await _storageService.savePendingAdultVerificationResult(result);
      return result;
    }

    final result = AdultVerificationResult(
      status: AdultVerificationStatus.inProgress,
      sessionId: identityVerificationId,
      provider: config.provider,
      message: '포트원 KG이니시스 본인인증을 진행하고 있어요.',
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  Future<AdultVerificationResult> mockVerifyAdult() async {
    _assertMockAllowed();
    return savePortOneSuccess(
      identityVerificationId: 'mock-${createIdentityVerificationId()}',
      identityVerificationTxId: 'mock-tx-${_uuid.v4()}',
      provider: providerMock,
      providerPayload: const {'mock': true},
    );
  }

  Future<AdultVerificationResult> mockFail() async {
    _assertMockAllowed();
    final result = AdultVerificationResult(
      status: AdultVerificationStatus.failed,
      sessionId: 'mock-${_uuid.v4()}',
      provider: providerMock,
      message: '본인인증이 완료되지 않았어요. 인증을 완료해야 가입을 계속할 수 있습니다.',
      providerPayload: const {'mock': true},
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  Future<AdultVerificationResult> mockCancel() async {
    _assertMockAllowed();
    final result = AdultVerificationResult(
      status: AdultVerificationStatus.cancelled,
      sessionId: 'mock-${_uuid.v4()}',
      provider: providerMock,
      message: '본인인증이 완료되지 않았어요. 인증을 완료해야 가입을 계속할 수 있습니다.',
      providerPayload: const {'mock': true},
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  Future<AdultVerificationResult> mockUnderAge() async {
    _assertMockAllowed();
    final result = AdultVerificationResult(
      status: AdultVerificationStatus.underAge,
      sessionId: 'mock-${_uuid.v4()}',
      provider: providerMock,
      message: '설레연은 연 나이 20세 이상만 이용할 수 있어요.',
      providerPayload: const {'mock': true},
    );
    await _storageService.savePendingAdultVerificationResult(result);
    return result;
  }

  void _assertMockAllowed() {
    if (!canUseMockVerification) {
      throw StateError('개발용 성인인증은 debug 빌드와 명시적인 개발 옵션에서만 사용할 수 있습니다.');
    }
  }
}
