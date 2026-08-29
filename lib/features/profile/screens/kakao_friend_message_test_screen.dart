import 'package:flutter/cupertino.dart';

import '../../../services/kakao_friend_invite_helper.dart';
import '../../../services/kakao_talk_friend_service.dart';

/// 카카오디벨로퍼스 심사 및 팀멤버 검증용 화면입니다.
/// 이 화면은 `KAKAO_REVIEW_TOOLS=true` 또는 debug 빌드에서만 진입시킵니다.
class KakaoFriendMessageTestScreen extends StatefulWidget {
  const KakaoFriendMessageTestScreen({super.key});

  @override
  State<KakaoFriendMessageTestScreen> createState() =>
      _KakaoFriendMessageTestScreenState();
}

class _KakaoFriendMessageTestScreenState
    extends State<KakaoFriendMessageTestScreen> {
  final KakaoTalkFriendService _service = KakaoTalkFriendService();

  bool _isLoading = false;
  bool? _isLoggedIn;
  int? _kakaoUserId;
  KakaoConsentStatus? _consentStatus;
  KakaoTalkFriendLookupResult? _friendResult;
  KakaoTalkMemoResult? _memoResult;
  KakaoTalkMessageResult? _messageResult;
  String? _lastError;
  DateTime? _lastTestAt;
  final List<String> _recentResults = [];

  Future<void> _run(String label, Future<void> Function() action) async {
    if (_isLoading) return;
    setState(() {
      _isLoading = true;
      _lastError = null;
    });
    try {
      await action();
      _append('$label 성공');
    } catch (error) {
      final message = _safeError(error);
      debugPrint('[KakaoReviewTest] $label failed: $message');
      if (mounted) setState(() => _lastError = message);
      _append('$label 실패: $message');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _checkLogin() {
    return _run('카카오 로그인 상태 확인', () async {
      final userId = await _service.checkLoginUserId();
      if (!mounted) return;
      setState(() {
        _isLoggedIn = userId != null;
        _kakaoUserId = userId;
      });
    });
  }

  Future<void> _requestConsents() {
    return _run('카카오 추가 동의 요청', () async {
      final status = await _service.ensureRequiredConsents(
        requireTalkMessage: true,
      );
      if (!mounted) return;
      setState(() {
        _consentStatus = status;
        _kakaoUserId = status.userId ?? _kakaoUserId;
      });
    });
  }

  Future<void> _fetchMe() {
    return _run('사용자정보조회 API', () async {
      final user = await _service.fetchCurrentUser();
      final status = await _service.getConsentStatus();
      if (!mounted) return;
      setState(() {
        _isLoggedIn = true;
        _kakaoUserId = user.id;
        _consentStatus = status;
      });
    });
  }

  Future<void> _fetchFriends() {
    return _run('Friend API 친구 목록 조회', () async {
      final result = await _service.fetchFriends();
      final status = await _service.getConsentStatus();
      if (!mounted) return;
      setState(() {
        _friendResult = result;
        _consentStatus = status;
      });
    });
  }

  Future<void> _sendMessageToMe() {
    return _run('Message API 나에게 보내기', () async {
      final result = await _service.sendTestMessageToMe();
      if (!mounted) return;
      setState(() => _memoResult = result);
      if (!result.sent) {
        throw Exception(result.errorMessage ?? '나에게 메시지 발송이 실패했어요.');
      }
    });
  }

  Future<void> _sendFirstFriendMessage() {
    return _run('Message API 테스트 메시지 발송', () async {
      var friends = _friendResult;
      friends ??= await _service.fetchFriends();
      final eligibleFriends = friends.friends
          .where((item) => item.hasUuid && item.canReceiveMessage)
          .toList(growable: false);
      final friend = eligibleFriends.isEmpty ? null : eligibleFriends.first;
      if (friend == null) {
        throw Exception('메시지를 받을 수 있는 카카오톡 친구가 조회되지 않았어요.');
      }

      final invite = await KakaoFriendInviteHelper.createKakaoInvitePayload();
      final result = await _service.sendMeetingInviteMessage(
        receiverUuid: friend.uuid,
        inviterName: '설레연 팀원',
        inviteUrl: Uri.parse(invite.inviteUrl),
      );
      if (!mounted) return;
      setState(() {
        _friendResult = friends;
        _messageResult = result;
      });
      if (!result.sent) {
        throw Exception(result.errorMessage ?? '메시지 발송 결과가 실패로 반환됐어요.');
      }
    });
  }

  void _append(String message) {
    final timestamp = DateTime.now();
    if (!mounted) return;
    setState(() {
      _lastTestAt = timestamp;
      _recentResults.insert(0, '${_time(timestamp)} $message');
      if (_recentResults.length > 8) _recentResults.removeLast();
    });
  }

  void _showRecentResults() {
    showCupertinoModalPopup<void>(
      context: context,
      builder: (sheetContext) => CupertinoActionSheet(
        title: const Text('최근 API 호출 결과'),
        message: Text(
          _recentResults.isEmpty
              ? '아직 호출 기록이 없어요.'
              : _recentResults.join('\n\n'),
          textAlign: TextAlign.left,
        ),
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(sheetContext).pop(),
          child: const Text('닫기'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final friend = _friendResult?.friends.isNotEmpty == true
        ? _friendResult!.friends.first
        : null;
    final memo = _memoResult;
    final message = _messageResult;

    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        middle: Text('Kakao Friend / Message Test'),
      ),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 36),
          children: [
            _statusCard('현재 상태', [
              '카카오 로그인: ${_boolText(_isLoggedIn)}',
              '카카오 user id: ${_maskId(_kakaoUserId)}',
              '친구목록 항목 사용 설정: ${_enabledText(_consentStatus?.friendsUsing)}',
              '친구목록 동의: ${_boolText(_consentStatus?.friendsAgreed)}',
              '메시지 항목 사용 설정: ${_enabledText(_consentStatus?.talkMessageUsing)}',
              '메시지 권한 동의: ${_boolText(_consentStatus?.talkMessageAgreed)}',
            ]),
            const SizedBox(height: 14),
            _actionButton('카카오 로그인 상태 확인', _checkLogin),
            _actionButton('카카오 추가 동의 요청', _requestConsents),
            _actionButton('사용자정보조회 API 호출', _fetchMe),
            _actionButton('Friend API 친구 목록 조회', _fetchFriends),
            _actionButton('나에게 Message API 테스트 메시지 보내기', _sendMessageToMe),
            _actionButton(
              '첫 번째 친구에게 Message API 테스트 메시지 보내기',
              _sendFirstFriendMessage,
            ),
            _actionButton(
              '최근 API 호출 결과 보기',
              () async => _showRecentResults(),
              primary: false,
            ),
            const SizedBox(height: 18),
            _statusCard('Friend API 결과', [
              '호출 상태: ${_friendResult == null ? '미호출' : '성공'}',
              '조회된 친구 수: ${_friendResult?.friends.length ?? 0}',
              '선택 후보 UUID: ${friend == null
                  ? '없음'
                  : friend.hasUuid
                  ? '있음 (${friend.maskedUuid})'
                  : '없음'}',
              if (friend != null) '첫 친구: ${friend.maskedNickname}',
            ]),
            const SizedBox(height: 14),
            _statusCard('Message API 나에게 보내기 결과', [
              '발송 상태: ${memo == null
                  ? '미호출'
                  : memo.sent
                  ? '성공'
                  : '실패'}',
              if (memo?.errorCode != null) '에러 코드: ${memo!.errorCode}',
              if (memo?.errorMessage != null) '에러 메시지: ${memo!.errorMessage}',
            ]),
            const SizedBox(height: 14),
            _statusCard('Message API 결과', [
              '발송 상태: ${message == null
                  ? '미호출'
                  : message.sent
                  ? '성공'
                  : '실패'}',
              '수신 UUID 존재: ${message == null
                  ? '미확인'
                  : message.receiverUuidExists
                  ? '있음'
                  : '없음'}',
              if (message?.errorCode != null) '에러 코드: ${message!.errorCode}',
              if (message?.errorMessage != null)
                '에러 메시지: ${message!.errorMessage}',
              '테스트 시간: ${_lastTestAt == null ? '없음' : _time(_lastTestAt!)}',
            ]),
            if (_lastError != null) ...[
              const SizedBox(height: 14),
              _statusCard('최근 오류', [_lastError!], isError: true),
            ],
            const SizedBox(height: 22),
            const Text(
              '카카오 Friend API는 조회 대상 친구도 해당 카카오디벨로퍼스 앱에 연결되어 있고, 친구목록/메시지 동의항목에 동의한 경우에만 조회됩니다. 심사용 테스트는 서로 카카오톡 친구인 팀멤버 2명 이상이 각각 설레연에 카카오 로그인하고 추가 동의를 완료한 뒤 진행해야 합니다.',
              style: TextStyle(
                fontSize: 13,
                height: 1.5,
                color: CupertinoColors.secondaryLabel,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actionButton(
    String label,
    Future<void> Function() onPressed, {
    bool primary = true,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: SizedBox(
        width: double.infinity,
        child: CupertinoButton(
          color: primary
              ? const Color(0xFFFEE500)
              : CupertinoColors.systemGrey5,
          onPressed: _isLoading ? null : onPressed,
          child: _isLoading
              ? const CupertinoActivityIndicator()
              : Text(
                  label,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: primary
                        ? const Color(0xFF181113)
                        : CupertinoColors.label,
                    fontWeight: FontWeight.w700,
                  ),
                ),
        ),
      ),
    );
  }

  Widget _statusCard(String title, List<String> lines, {bool isError = false}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isError
            ? CupertinoColors.systemRed.withValues(alpha: 0.08)
            : CupertinoColors.secondarySystemBackground,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          ...lines.map(
            (line) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                line,
                style: const TextStyle(fontSize: 13, height: 1.35),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _boolText(bool? value) => value == null
      ? '미확인'
      : value
      ? '동의함'
      : '미동의';

  String _enabledText(bool? value) => value == null
      ? '미확인'
      : value
      ? '사용 중'
      : '사용 안 함';

  String _maskId(int? value) {
    if (value == null) return '미확인';
    final text = value.toString();
    return text.length <= 4 ? '****' : '${text.substring(0, 4)}...';
  }

  String _time(DateTime value) {
    String two(int input) => input.toString().padLeft(2, '0');
    return '${two(value.hour)}:${two(value.minute)}:${two(value.second)}';
  }

  String _safeError(Object error) {
    return error
        .toString()
        .replaceFirst('Exception: ', '')
        .replaceAll(
          RegExp(r'access[_ -]?token[^, ]*', caseSensitive: false),
          '[redacted]',
        )
        .replaceAll(
          RegExp(r'refresh[_ -]?token[^, ]*', caseSensitive: false),
          '[redacted]',
        );
  }
}
