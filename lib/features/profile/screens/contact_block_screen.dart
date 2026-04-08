import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';

import '../../../services/contact_block_service.dart';
import '../../../utils/helpers.dart';

class _AppColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF89616B);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color emerald500 = Color(0xFF10B981);
}

class ContactBlockScreen extends StatefulWidget {
  const ContactBlockScreen({super.key});

  @override
  State<ContactBlockScreen> createState() => _ContactBlockScreenState();
}

class _ContactBlockScreenState extends State<ContactBlockScreen> {
  final _service = ContactBlockService();

  bool _isSyncing = false;
  ContactBlockSyncResult? _result;
  String? _error;
  DateTime? _lastSyncTime;

  @override
  void initState() {
    super.initState();
    _loadLastSync();
  }

  Future<void> _loadLastSync() async {
    final t = await _service.getLastSyncTime();
    if (mounted) setState(() => _lastSyncTime = t);
  }

  Future<void> _startSync() async {
    HapticFeedback.mediumImpact();
    setState(() {
      _isSyncing = true;
      _error = null;
      _result = null;
    });

    try {
      final permission = await _service.checkPermission();

      if (!mounted) return;

      if (permission == ContactPermissionStatus.permanentlyDenied) {
        setState(() {
          _isSyncing = false;
          _error = 'permanentlyDenied';
        });
        return;
      }

      if (permission == ContactPermissionStatus.denied) {
        setState(() {
          _isSyncing = false;
          _error = 'denied';
        });
        return;
      }

      final result = await _service.syncContacts();
      await _service.saveLastSyncTime();
      final lastSync = await _service.getLastSyncTime();

      if (!mounted) return;
      setState(() {
        _result = result;
        _lastSyncTime = lastSync;
        _isSyncing = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _isSyncing = false;
      });
    }
  }

  Future<void> _openAppSettings() async {
    try {
      await FlutterContacts.permissions.openSettings();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.surfaceLight.withValues(alpha: 0.8),
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pop();
          },
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: CupertinoColors.black.withValues(alpha: 0.05),
            ),
            child: const Icon(
              CupertinoIcons.back,
              size: 20,
              color: _AppColors.textMain,
            ),
          ),
        ),
        middle: const Text(
          '연락처 차단',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 48),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildExplanationCard(),
              const SizedBox(height: 24),
              _buildPrivacyInfo(),
              const SizedBox(height: 32),
              _buildSyncButton(),
              if (_lastSyncTime != null) ...[
                const SizedBox(height: 16),
                _buildLastSyncInfo(),
              ],
              if (_result != null) ...[
                const SizedBox(height: 24),
                _buildResultCard(),
              ],
              if (_error != null) ...[
                const SizedBox(height: 24),
                _buildErrorCard(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildExplanationCard() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.08),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  CupertinoIcons.person_badge_minus,
                  size: 24,
                  color: _AppColors.primary,
                ),
              ),
              const SizedBox(width: 16),
              const Expanded(
                child: Text(
                  '내 연락처의 지인이\n설레연에서 추천되지 않도록',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          _infoRow(
            CupertinoIcons.shield_lefthalf_fill,
            '연락처에 저장된 지인과 서로 추천되지 않아요.',
          ),
          const SizedBox(height: 12),
          _infoRow(
            CupertinoIcons.chat_bubble,
            '기존 매치나 채팅은 그대로 유지돼요.',
          ),
          const SizedBox(height: 12),
          _infoRow(
            CupertinoIcons.eye_slash,
            '상대방에게 차단 사실이 알려지지 않아요.',
          ),
        ],
      ),
    );
  }

  Widget _infoRow(IconData icon, String text) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: _AppColors.textSecondary),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: _AppColors.textSecondary,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPrivacyInfo() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F9FF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFBAE6FD)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(CupertinoIcons.lock_shield, size: 18, color: Color(0xFF0284C7)),
              SizedBox(width: 8),
              Text(
                '개인정보 보호 안내',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF0284C7),
                ),
              ),
            ],
          ),
          SizedBox(height: 12),
          Text(
            '• 연락처의 전화번호만 사용하며, 이름이나 기타 정보는 서버에 전송되지 않아요.\n'
            '• 전화번호는 기기에서 안전하게 암호화(해시)된 후 전송되며, 원본 전화번호는 서버에 저장되지 않아요.\n'
            '• 연락처 권한을 해제해도 이미 적용된 차단은 유지돼요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              color: Color(0xFF0369A1),
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSyncButton() {
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: const EdgeInsets.symmetric(vertical: 16),
        borderRadius: BorderRadius.circular(16),
        color: _AppColors.primary,
        onPressed: _isSyncing ? null : _startSync,
        child: _isSyncing
            ? const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CupertinoActivityIndicator(color: CupertinoColors.white),
                  SizedBox(width: 12),
                  Text(
                    '연락처 동기화 중...',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: CupertinoColors.white,
                    ),
                  ),
                ],
              )
            : Text(
                _lastSyncTime != null ? '다시 동기화하기' : '연락처 차단 시작하기',
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: CupertinoColors.white,
                ),
              ),
      ),
    );
  }

  Widget _buildLastSyncInfo() {
    final timeStr = _lastSyncTime != null
        ? Helpers.getRelativeTime(_lastSyncTime!)
        : '';
    return Center(
      child: Text(
        '마지막 동기화: $timeStr',
        style: const TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 13,
          color: _AppColors.gray400,
        ),
      ),
    );
  }

  Widget _buildResultCard() {
    final r = _result!;
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: _AppColors.emerald500.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(CupertinoIcons.checkmark_circle_fill,
                  size: 24, color: _AppColors.emerald500),
              SizedBox(width: 10),
              Text(
                '연락처 차단이 적용되었어요',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          _resultRow('전체 연락처', '${r.totalContacts}명'),
          _resultRow('유효한 전화번호', '${r.validPhoneCount}개'),
          _resultRow('중복 제거 후', '${r.uniqueHashCount}개'),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Container(height: 1, color: _AppColors.gray100),
          ),
          _resultRow(
            '설레연 사용자 매칭',
            '${r.matchedUserCount}명',
            highlight: true,
          ),
          _resultRow(
            '새로 상호 차단',
            '${r.newlyBlockedPairCount}쌍',
            highlight: true,
          ),
          if (r.alreadyBlockedPairCount > 0)
            _resultRow('이미 차단됨', '${r.alreadyBlockedPairCount}쌍'),
          const SizedBox(height: 16),
          const Text(
            '앞으로 차단된 사용자와 서로 추천되지 않아요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _resultRow(String label, String value, {bool highlight = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color:
                  highlight ? _AppColors.textMain : _AppColors.textSecondary,
              fontWeight: highlight ? FontWeight.w600 : FontWeight.w400,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: highlight ? _AppColors.primary : _AppColors.gray800,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorCard() {
    final isPermanent = _error == 'permanentlyDenied';
    final isDenied = _error == 'denied';

    String title;
    String message;
    if (isPermanent) {
      title = '연락처 접근 권한이 필요해요';
      message =
          '설정에서 설레연의 연락처 접근 권한을 허용해 주세요.\n'
          '권한을 허용하면 연락처 차단 기능을 사용할 수 있어요.';
    } else if (isDenied) {
      title = '연락처 접근이 거부되었어요';
      message = '연락처 차단 기능을 사용하려면 연락처 접근 권한이 필요해요.';
    } else {
      title = '오류가 발생했어요';
      message = _error ?? '알 수 없는 오류가 발생했어요.';
    }

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFFECACA)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(CupertinoIcons.exclamationmark_triangle,
                  size: 20, color: Color(0xFFDC2626)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFFDC2626),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            message,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              color: Color(0xFF991B1B),
              height: 1.5,
            ),
          ),
          if (isPermanent) ...[
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: CupertinoButton(
                padding: const EdgeInsets.symmetric(vertical: 12),
                borderRadius: BorderRadius.circular(12),
                color: _AppColors.gray800,
                onPressed: _openAppSettings,
                child: const Text(
                  '설정으로 이동',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: CupertinoColors.white,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
