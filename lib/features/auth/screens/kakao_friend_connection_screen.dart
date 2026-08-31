import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';

import '../../../router/route_names.dart';
import '../../../services/account_setup_flow.dart';
import '../../../services/kakao_friend_connection_service.dart';
import '../../../shared/utils/privacy_log_utils.dart';

/// 카카오 친구 연결 화면 (로그인 화면이 아니다).
///
/// 인증은 이미 연세 이메일로 끝난 상태이며, 이 화면의 카카오 OAuth 는 오직
/// "아는 사람 추천 차단"(friend exclusion) 권한 연결에만 쓰인다. 연결 성공은
/// 어떤 인증 상태도 바꾸지 않으며, 건너뛰기/미루기 선택지는 제공하지 않는다.
class KakaoFriendConnectionScreen extends StatefulWidget {
  const KakaoFriendConnectionScreen({super.key});

  @override
  State<KakaoFriendConnectionScreen> createState() =>
      _KakaoFriendConnectionScreenState();
}

class _KakaoFriendConnectionScreenState
    extends State<KakaoFriendConnectionScreen> {
  final KakaoFriendConnectionService _connectionService =
      KakaoFriendConnectionService();
  final AccountSetupFlow _setupFlow = AccountSetupFlow();

  bool _isConnecting = false;
  bool _consentRefused = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    // App-restart resume: if a previous run already completed the connection
    // (or the user must first re-do email auth), route without re-linking.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _resumeIfAlreadyResolved();
    });
  }

  Future<void> _resumeIfAlreadyResolved() async {
    if (FirebaseAuth.instance.currentUser == null) {
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(RouteNames.login);
      return;
    }
    try {
      final ready = await _connectionService.verifyFriendConnectionReady();
      if (ready && mounted) {
        await _navigateAfterConnection();
      }
    } catch (e) {
      debugPrint(
        '[KakaoConnect] resume check skipped: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  Future<void> _navigateAfterConnection() async {
    final route = await _setupFlow.resolveNextRoute();
    if (!mounted) return;
    Navigator.of(context).pushNamedAndRemoveUntil(route, (r) => false);
  }

  Future<void> _connect() async {
    if (_isConnecting) return;
    setState(() {
      _isConnecting = true;
      _errorMessage = null;
      _consentRefused = false;
    });

    try {
      await _connectionService.runFullConnectionFlow();
      if (!mounted) return;
      await _navigateAfterConnection();
    } on KakaoFriendConnectionException catch (e) {
      if (e.consentRefused) {
        // 동의 거절 시에도 서버는 fail-closed pending 상태로 남긴다.
        await _connectionService.markPendingAfterConsentRefusal();
      }
      if (!mounted) return;
      setState(() {
        _errorMessage = e.userMessage;
        _consentRefused = e.consentRefused;
      });
    } on StateError catch (e) {
      debugPrint(
        '[KakaoConnect] precondition failed: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!mounted) return;
      if (e.message == 'primary_email_auth_required') {
        Navigator.of(context).pushReplacementNamed(RouteNames.login);
        return;
      }
      setState(() => _errorMessage = '친구 연결을 완료하지 못했어요. 다시 시도해 주세요.');
    } catch (e) {
      debugPrint(
        '[KakaoConnect] connect failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (!mounted) return;
      setState(() => _errorMessage = '친구 연결을 완료하지 못했어요. 다시 시도해 주세요.');
    } finally {
      if (mounted) setState(() => _isConnecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return KakaoFriendConnectionView(
      isConnecting: _isConnecting,
      consentRefused: _consentRefused,
      errorMessage: _errorMessage,
      onConnectPressed: _connect,
    );
  }
}

/// Pure presentational body of the Kakao friend connection screen.
/// Kept widget-testable without Firebase/Kakao plumbing.
class KakaoFriendConnectionView extends StatelessWidget {
  const KakaoFriendConnectionView({
    super.key,
    required this.isConnecting,
    required this.consentRefused,
    required this.errorMessage,
    required this.onConnectPressed,
  });

  final bool isConnecting;
  final bool consentRefused;
  final String? errorMessage;
  final VoidCallback onConnectPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      navigationBar: const CupertinoNavigationBar(middle: Text('카카오 친구 연결')),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              const Text(
                '아는 사람 추천 차단을 위해\n카카오 친구를 연결해 주세요',
                style: TextStyle(
                  fontSize: 24,
                  height: 1.32,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A),
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                '친구 목록은 아는 사람이 1:1 추천에 등장하지 않도록 제외 여부를 확인하는 데에만 사용해요.\n'
                '점수 계산, 광고, 프로필 노출에는 절대 사용하지 않아요.',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.45,
                  color: Color(0xFF64748B),
                ),
              ),
              const SizedBox(height: 18),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: consentRefused
                      ? const Color(0xFFFFF7E6)
                      : const Color(0xFFF3F6FF),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: consentRefused
                        ? const Color(0xFFFFD37A)
                        : const Color(0xFFD7E1FF),
                  ),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      consentRefused
                          ? CupertinoIcons.exclamationmark_shield_fill
                          : CupertinoIcons.shield_fill,
                      size: 22,
                      color: consentRefused
                          ? const Color(0xFFB54708)
                          : const Color(0xFF4969D8),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        consentRefused
                            ? '친구목록 동의가 완료되지 않았어요. 아는 사람 추천 차단을 위해 동의가 꼭 필요해요.'
                            : '친구의 이름이나 프로필은 저장하지 않으며, 설레연 사용자 간 추천 제외 여부를 확인하는 데만 사용해요.',
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.4,
                          fontWeight: FontWeight.w500,
                          color: consentRefused
                              ? const Color(0xFF7A2E0E)
                              : const Color(0xFF3854B5),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              if (errorMessage != null) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFE8EA),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFFFC2CC)),
                  ),
                  child: Text(
                    errorMessage!,
                    style: const TextStyle(
                      fontSize: 13,
                      color: Color(0xFFB42318),
                      height: 1.35,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
              ],
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 56,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  borderRadius: BorderRadius.circular(28),
                  color: const Color(0xFFFEE500),
                  onPressed: isConnecting ? null : onConnectPressed,
                  child: isConnecting
                      ? const CupertinoActivityIndicator(
                          color: Color(0xFF191919),
                        )
                      : Text(
                          consentRefused ? '다시 동의하고 친구 연결하기' : '카카오 친구 연결하기',
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF191919),
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 10),
              const Center(
                child: Text(
                  '친구 연결을 완료해야 추천 기능을 사용할 수 있어요.',
                  style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
