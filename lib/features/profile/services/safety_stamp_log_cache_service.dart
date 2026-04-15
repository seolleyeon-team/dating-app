import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/safety_stamp_log_entry.dart';

class SafetyStampLogCacheService {
  static const String _cacheKeyPrefix = 'safety_stamp_logs_';

  Future<List<SafetyStampLogEntry>> getLogs(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_cacheKeyPrefix + userId);
    if (raw == null || raw.trim().isEmpty) {
      return const <SafetyStampLogEntry>[];
    }

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <SafetyStampLogEntry>[];
      }

      final logs = decoded
          .whereType<Map>()
          .map(
            (item) =>
                SafetyStampLogEntry.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList();
      logs.sort((a, b) => b.stampedAt.compareTo(a.stampedAt));
      return logs;
    } catch (_) {
      return const <SafetyStampLogEntry>[];
    }
  }

  Future<void> saveLog(String userId, SafetyStampLogEntry log) async {
    final prefs = await SharedPreferences.getInstance();
    final logs = await getLogs(userId);

    final nextLogs = [log, ...logs.where((item) => item.logId != log.logId)]
      ..sort((a, b) => b.stampedAt.compareTo(a.stampedAt));

    await prefs.setString(
      _cacheKeyPrefix + userId,
      jsonEncode(nextLogs.map((item) => item.toJson()).toList()),
    );
  }
}
