import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../../../services/firebase_runtime.dart';

class SupportUserSummary {
  final String userId;
  final String nickname;
  final String university;
  final String? avatarUrl;

  const SupportUserSummary({
    required this.userId,
    required this.nickname,
    required this.university,
    this.avatarUrl,
  });

  factory SupportUserSummary.fromMap(Map<String, dynamic> data) {
    return SupportUserSummary(
      userId: data['userId']?.toString() ?? '',
      nickname: data['nickname']?.toString() ?? '이름 미설정',
      university: data['university']?.toString() ?? '',
      avatarUrl: data['avatarUrl']?.toString(),
    );
  }
}

class SupportUserPage {
  final List<SupportUserSummary> users;
  final String? nextPageToken;

  const SupportUserPage({required this.users, this.nextPageToken});
}

class SupportChatService {
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: firebaseFunctionsRegion,
  );

  Future<bool> isOperations() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return false;
    final token = await user.getIdTokenResult();
    return token.claims?['operations'] == true;
  }

  Future<SupportUserPage> listUsers({
    String search = '',
    String? pageToken,
  }) async {
    final result = await _functions
        .httpsCallable('listSupportUsers')
        .call<dynamic>({
          'pageSize': 50,
          'search': search.trim(),
          if (pageToken != null && pageToken.isNotEmpty) 'pageToken': pageToken,
        });
    final data = Map<String, dynamic>.from(result.data as Map? ?? const {});
    final rawUsers = data['users'];
    if (rawUsers is! List) return const SupportUserPage(users: []);
    return SupportUserPage(
      users: rawUsers
          .whereType<Map>()
          .map(
            (value) =>
                SupportUserSummary.fromMap(Map<String, dynamic>.from(value)),
          )
          .where((user) => user.userId.isNotEmpty)
          .toList(),
      nextPageToken: data['nextPageToken']?.toString(),
    );
  }

  Future<String> openSupportChat(String userId) async {
    final result = await _functions
        .httpsCallable('openSupportChat')
        .call<dynamic>({'userId': userId});
    final data = Map<String, dynamic>.from(result.data as Map? ?? const {});
    final roomId = data['roomId']?.toString() ?? '';
    if (roomId.isEmpty) throw StateError('Support room id is missing');
    return roomId;
  }
}
