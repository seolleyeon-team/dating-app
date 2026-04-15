import 'package:flutter/cupertino.dart';

import '../../../services/storage_service.dart';
import '../models/safety_stamp_log_entry.dart';
import '../services/safety_stamp_log_cache_service.dart';

class _AppColors {
  static const Color background = Color(0xFFF8F6F6);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF89616B);
  static const Color pink = Color(0xFFF0426E);
  static const Color pinkSoft = Color(0xFFFFF1F5);
  static const Color mint = Color(0xFF1F9D7A);
  static const Color mintSoft = Color(0xFFEEF9F5);
  static const Color border = Color(0xFFF1E4E8);
}

class SafetyStampLogScreen extends StatefulWidget {
  const SafetyStampLogScreen({super.key});

  @override
  State<SafetyStampLogScreen> createState() => _SafetyStampLogScreenState();
}

class _SafetyStampLogScreenState extends State<SafetyStampLogScreen> {
  final StorageService _storageService = StorageService();
  final SafetyStampLogCacheService _logCacheService =
      SafetyStampLogCacheService();

  Future<List<SafetyStampLogEntry>>? _logsFuture;

  @override
  void initState() {
    super.initState();
    _logsFuture = _loadLogs();
  }

  Future<List<SafetyStampLogEntry>> _loadLogs() async {
    final userId = await _storageService.getKakaoUserId();
    if (userId == null || userId.isEmpty) {
      return const <SafetyStampLogEntry>[];
    }
    return _logCacheService.getLogs(userId);
  }

  String _formatDateTime(DateTime dateTime) {
    final period = dateTime.hour >= 12 ? '오후' : '오전';
    final hour12 = dateTime.hour == 0
        ? 12
        : (dateTime.hour > 12 ? dateTime.hour - 12 : dateTime.hour);
    final minute = dateTime.minute.toString().padLeft(2, '0');
    return '${dateTime.month}월 ${dateTime.day}일 $period $hour12:$minute';
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.background,
      navigationBar: const CupertinoNavigationBar(
        middle: Text(
          '안전도장 로그',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: FutureBuilder<List<SafetyStampLogEntry>>(
          future: _logsFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CupertinoActivityIndicator());
            }

            final logs = snapshot.data ?? const <SafetyStampLogEntry>[];
            if (logs.isEmpty) {
              return const Center(
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32),
                  child: Text(
                    '아직 저장된 안전도장 로그가 없어요.\n새 만남이나 헤어짐 도장을 찍으면 여기에 최신순으로 기록돼요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 15,
                      height: 1.5,
                      color: _AppColors.textSub,
                    ),
                  ),
                ),
              );
            }

            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
              itemBuilder: (context, index) {
                final log = logs[index];
                final chipColor = log.isGoodbyeStamp
                    ? _AppColors.mintSoft
                    : _AppColors.pinkSoft;
                final chipTextColor = log.isGoodbyeStamp
                    ? _AppColors.mint
                    : _AppColors.pink;

                return Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: _AppColors.surface,
                    borderRadius: BorderRadius.circular(22),
                    border: Border.all(color: _AppColors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: chipColor,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          log.phaseLabel,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: chipTextColor,
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      Text(
                        '${log.partnerName}님과의 기록',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 12),
                      _LogMetaRow(
                        label: '찍은 시간',
                        value: _formatDateTime(log.stampedAt),
                      ),
                      const SizedBox(height: 8),
                      _LogMetaRow(label: '찍은 장소', value: log.placeName),
                    ],
                  ),
                );
              },
              separatorBuilder: (_, __) => const SizedBox(height: 14),
              itemCount: logs.length,
            );
          },
        ),
      ),
    );
  }
}

class _LogMetaRow extends StatelessWidget {
  const _LogMetaRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 68,
          child: Text(
            label,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: _AppColors.textSub,
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: _AppColors.textMain,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}
