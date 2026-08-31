import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:portone_flutter/v2/model/entity/bypass/identity_verification/inicis_unified.dart';
import 'package:portone_flutter/v2/model/entity/bypass/identity_verification/inicis_unified_flg_fixed_user.dart';
import 'package:portone_flutter/v2/model/entity/bypass/identity_verification_bypass.dart';
import 'package:portone_flutter/v2/model/request/identity_verification_request.dart';
import 'package:portone_flutter/v2/model/response/identity_verification_response.dart';
import 'package:portone_flutter/v2/portone_identity_verification.dart';

import '../../../config/portone_config.dart';
import '../../../router/route_names.dart';
import '../../../services/adult_verification_result.dart';
import '../../../services/adult_verification_service.dart';

class AdultVerificationGateScreen extends StatefulWidget {
  const AdultVerificationGateScreen({super.key});

  @override
  State<AdultVerificationGateScreen> createState() =>
      _AdultVerificationGateScreenState();
}

class _AdultVerificationGateScreenState
    extends State<AdultVerificationGateScreen> {
  final AdultVerificationService _verificationService =
      AdultVerificationService();

  AdultVerificationResult _result = AdultVerificationResult.notStarted;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSession();
  }

  Future<void> _loadSession() async {
    final result = await _verificationService.getPendingSession();
    if (!mounted) return;
    setState(() {
      _result = result;
      _isLoading = false;
    });
  }

  Future<void> _startVerification() async {
    if (_isLoading) return;
    HapticFeedback.mediumImpact();
    setState(() {
      _isLoading = true;
      _result = _result.copyWith(status: AdultVerificationStatus.inProgress);
    });

    final config = AdultVerificationConfig.fromEnvironment;
    if (!config.isPortOneConfigured) {
      final result = await _verificationService.saveFailure(
        status: AdultVerificationStatus.failed,
        message: '포트원 KG이니시스 테스트 채널 설정이 필요해요.',
      );
      if (!mounted) return;
      setState(() {
        _result = result;
        _isLoading = false;
      });
      return;
    }

    final inProgress = await _verificationService.startVerification(
      config: config,
    );
    if (!mounted) return;
    setState(() {
      _result = inProgress;
      _isLoading = false;
    });

    final response = await Navigator.of(context)
        .push<IdentityVerificationResponse>(
          CupertinoPageRoute(
            fullscreenDialog: true,
            builder: (_) => PortoneIdentityVerification(
              appBar: const CupertinoNavigationBar(middle: Text('본인인증')),
              appScheme: PortOneConfig.appScheme,
              initialChild: const Center(
                child: CupertinoActivityIndicator(color: Color(0xFFFF6B8A)),
              ),
              data: IdentityVerificationRequest(
                storeId: config.storeId,
                identityVerificationId: inProgress.sessionId!,
                channelKey: config.channelKey,
                bypass: IdentityVerificationBypass(
                  inicisUnified: InicisUnifiedIdentityVerificationBypass(
                    flgFixedUser: InicisUnifiedFlgFixedUser.N,
                  ),
                ),
              ),
              callback: (response) {
                Navigator.of(context).pop(response);
              },
            ),
          ),
        );

    if (!mounted) return;
    final result = response == null
        ? await _verificationService.saveFailure(
            status: AdultVerificationStatus.cancelled,
            identityVerificationId: inProgress.sessionId,
            message: '본인인증이 완료되지 않았어요. 인증을 완료해야 가입을 계속할 수 있습니다.',
          )
        : await _handlePortOneResponse(response);

    if (!mounted) return;
    setState(() => _result = result);
  }

  Future<void> _runMock(
    Future<AdultVerificationResult> Function() action,
  ) async {
    setState(() => _isLoading = true);
    final result = await action();
    if (!mounted) return;
    setState(() {
      _result = result;
      _isLoading = false;
    });
  }

  Future<AdultVerificationResult> _handlePortOneResponse(
    IdentityVerificationResponse response,
  ) async {
    final code = response.code?.trim();
    final message = response.message?.trim();
    final payload = response.toJson();

    if (code == null || code.isEmpty) {
      return _verificationService.savePortOneSuccess(
        identityVerificationId: response.identityVerificationId,
        identityVerificationTxId: response.identityVerificationTxId,
        providerPayload: payload,
      );
    }

    final lowerCode = code.toLowerCase();
    final lowerMessage = message?.toLowerCase() ?? '';
    final isCancelled =
        lowerCode.contains('cancel') ||
        lowerMessage.contains('cancel') ||
        message == '사용자가 본인인증을 취소했습니다.';

    return _verificationService.saveFailure(
      status: isCancelled
          ? AdultVerificationStatus.cancelled
          : AdultVerificationStatus.failed,
      identityVerificationId: response.identityVerificationId,
      identityVerificationTxId: response.identityVerificationTxId,
      message: isCancelled
          ? '본인인증이 완료되지 않았어요. 인증을 완료해야 가입을 계속할 수 있습니다.'
          : message ?? '본인인증에 실패했어요. 다시 시도해 주세요.',
      providerPayload: payload,
    );
  }

  void _goToEmailLogin() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(RouteNames.login);
    });
  }

  Future<void> _handlePrimaryAction() async {
    if (_result.canProceedToKakao) {
      _goToEmailLogin();
      return;
    }
    await _startVerification();
  }

  String? get _statusMessage {
    if (_result.status == AdultVerificationStatus.underAge) {
      return '설레연은 연 나이 20세 이상만 이용할 수 있어요.';
    }
    if (_result.canProceedToKakao) {
      return '본인인증이 완료되었어요.\n이제 연세 이메일 로그인을 진행해 주세요.';
    }
    if (_result.status == AdultVerificationStatus.pendingServerVerification) {
      return '로그인 후 본인인증 결과를 서버에서 확인하고 있어요.';
    }
    if (_result.status == AdultVerificationStatus.failed ||
        _result.status == AdultVerificationStatus.cancelled) {
      return _result.message ?? '본인인증이 완료되지 않았어요. 인증을 완료해야 가입을 계속할 수 있습니다.';
    }
    if (_result.status == AdultVerificationStatus.inProgress) {
      return '본인인증을 진행하고 있어요.';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final canUseMock = _verificationService.canUseMockVerification;
    final canProceedToKakao = _result.canProceedToKakao;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      navigationBar: const CupertinoNavigationBar(middle: Text('본인인증')),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(
                  color: const Color(0xFFFF6B8A).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: const Icon(
                  CupertinoIcons.checkmark_shield_fill,
                  color: Color(0xFFFF6B8A),
                  size: 30,
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                '본인인증이 필요해요',
                style: TextStyle(
                  fontSize: 26,
                  height: 1.28,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                '설레연은 안전한 서비스 운영과 청소년 이용 제한을 위해 본인인증을 진행합니다.\n인증된 이름과 휴대전화번호는 신고 및 분쟁 대응, 중복 가입 방지, 성인 여부 확인 목적으로만 사용되며 다른 사용자에게 공개되지 않습니다.\n본인인증을 완료해야 연세 이메일 로그인을 진행할 수 있어요.',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.55,
                  fontWeight: FontWeight.w500,
                  color: Color(0xFF64748B),
                ),
              ),
              const SizedBox(height: 22),
              if (_statusMessage != null)
                _StatusNotice(
                  message: _statusMessage!,
                  isBlocking:
                      _result.status == AdultVerificationStatus.underAge,
                ),
              if (canUseMock) ...[
                const SizedBox(height: 14),
                const _MockNotice(),
              ],
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 56,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  borderRadius: BorderRadius.circular(28),
                  color: const Color(0xFFFF6B8A),
                  onPressed: _isLoading ? null : _handlePrimaryAction,
                  child: _isLoading
                      ? const CupertinoActivityIndicator(color: Colors.white)
                      : Text(
                          canProceedToKakao ? '이메일 로그인 진행하기' : '본인인증 시작하기',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                ),
              ),
              if (canProceedToKakao) ...[
                const SizedBox(height: 10),
                Center(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    onPressed: _isLoading ? null : _startVerification,
                    child: const Text(
                      '다시 본인인증하기',
                      style: TextStyle(fontSize: 14, color: Color(0xFF64748B)),
                    ),
                  ),
                ),
              ],
              if (canUseMock) ...[
                const SizedBox(height: 12),
                _MockButtons(
                  enabled: !_isLoading,
                  onSuccess: () =>
                      _runMock(_verificationService.mockVerifyAdult),
                  onFail: () => _runMock(_verificationService.mockFail),
                  onCancel: () => _runMock(_verificationService.mockCancel),
                  onUnderAge: () => _runMock(_verificationService.mockUnderAge),
                ),
              ],
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusNotice extends StatelessWidget {
  const _StatusNotice({required this.message, required this.isBlocking});

  final String message;
  final bool isBlocking;

  @override
  Widget build(BuildContext context) {
    final bgColor = isBlocking
        ? const Color(0xFFFFE8EA)
        : const Color(0xFFFFF4E5);
    final borderColor = isBlocking
        ? const Color(0xFFFFC2CC)
        : const Color(0xFFFFD9A8);
    final textColor = isBlocking
        ? const Color(0xFFB42318)
        : const Color(0xFF9A5B00);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: borderColor),
      ),
      child: Text(
        message,
        style: TextStyle(
          fontSize: 14,
          height: 1.45,
          fontWeight: FontWeight.w600,
          color: textColor,
        ),
      ),
    );
  }
}

class _MockNotice extends StatelessWidget {
  const _MockNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Text(
        kDebugMode
            ? '개발용 테스트 인증입니다. release/prod 빌드에서는 노출되거나 성공 처리되지 않습니다.'
            : '개발용 테스트 인증은 현재 빌드에서 사용할 수 없습니다.',
        style: const TextStyle(
          fontSize: 13,
          height: 1.45,
          fontWeight: FontWeight.w600,
          color: Color(0xFF475569),
        ),
      ),
    );
  }
}

class _MockButtons extends StatelessWidget {
  const _MockButtons({
    required this.enabled,
    required this.onSuccess,
    required this.onFail,
    required this.onCancel,
    required this.onUnderAge,
  });

  final bool enabled;
  final VoidCallback onSuccess;
  final VoidCallback onFail;
  final VoidCallback onCancel;
  final VoidCallback onUnderAge;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MockChip(label: '개발용 성공', enabled: enabled, onPressed: onSuccess),
        _MockChip(label: '실패', enabled: enabled, onPressed: onFail),
        _MockChip(label: '취소', enabled: enabled, onPressed: onCancel),
        _MockChip(label: '미성년자', enabled: enabled, onPressed: onUnderAge),
      ],
    );
  }
}

class _MockChip extends StatelessWidget {
  const _MockChip({
    required this.label,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      minimumSize: const Size(0, 36),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      borderRadius: BorderRadius.circular(18),
      color: const Color(0xFFE2E8F0),
      disabledColor: const Color(0xFFF1F5F9),
      onPressed: enabled ? onPressed : null,
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: Color(0xFF334155),
        ),
      ),
    );
  }
}
