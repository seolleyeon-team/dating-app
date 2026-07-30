import 'package:intl/intl.dart';

class Helpers {
  // Format Phone Number
  static String formatPhoneNumber(String phone) {
    final cleaned = phone.replaceAll(RegExp(r'[\s-]'), '');
    if (cleaned.length == 11) {
      return '${cleaned.substring(0, 3)}-${cleaned.substring(3, 7)}-${cleaned.substring(7)}';
    }
    return phone;
  }

  // Format Date
  static String formatDate(DateTime date, {String format = 'yyyy-MM-dd'}) {
    return DateFormat(format).format(date);
  }

  // Format DateTime
  static String formatDateTime(
    DateTime dateTime, {
    String format = 'yyyy-MM-dd HH:mm',
  }) {
    return DateFormat(format).format(dateTime);
  }

  // Get Relative Time (e.g., "2시간 전", "3일 전")
  static String getRelativeTime(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inDays > 365) {
      return '${(difference.inDays / 365).floor()}년 전';
    } else if (difference.inDays > 30) {
      return '${(difference.inDays / 30).floor()}개월 전';
    } else if (difference.inDays > 0) {
      return '${difference.inDays}일 전';
    } else if (difference.inHours > 0) {
      return '${difference.inHours}시간 전';
    } else if (difference.inMinutes > 0) {
      return '${difference.inMinutes}분 전';
    } else {
      return '방금 전';
    }
  }

  // Validate and Format Phone Number
  static String? validateAndFormatPhone(String? phone) {
    if (phone == null || phone.isEmpty) return null;
    final cleaned = phone.replaceAll(RegExp(r'[\s-]'), '');
    if (cleaned.length == 11 && cleaned.startsWith('010')) {
      return formatPhoneNumber(cleaned);
    }
    return null;
  }
}
