class AppConstants {
  // App Info
  static const String appName = '설레연';
  static const String appDescription = '연세대학교 데이팅 앱';
  
  // API Endpoints
  static const String baseUrl = 'https://api.example.com'; // TODO: Replace with actual URL
  static const String apiVersion = '/v1';
  
  // Storage Keys
  static const String userIdKey = 'user_id';
  static const String isFirstLaunchKey = 'is_first_launch';
  static const String hasSeenTutorialKey = 'has_seen_tutorial';
  static const String authTokenKey = 'auth_token';
  
  // Gender Options
  static const List<String> genders = ['남성', '여성'];
  
  // Major Categories
  static const List<String> majorCategories = ['문과', '이과', '예체', '메디컬'];
  
  // MBTI Types
  static const List<String> mbtiTypes = [
    'INTJ', 'INTP', 'ENTJ', 'ENTP',
    'INFJ', 'INFP', 'ENFJ', 'ENFP',
    'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
    'ISTP', 'ISFP', 'ESTP', 'ESFP',
  ];
  
  // Attachment Types
  static const List<String> attachmentTypes = [
    '안정형',
    '회피형',
    '불안형',
  ];
  
  // Money System
  static const int defaultMoney = 0;
  static const int matchingCost = 100; // 매칭 비용
  static const int meetingDeposit = 5000; // 미팅 예치금
}
