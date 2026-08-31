import 'package:cloud_functions/cloud_functions.dart';
import 'package:uuid/uuid.dart';

import '../../../services/auth_service.dart';
import '../../../services/firebase_runtime.dart';
import '../../../services/storage_service.dart';

/// 서버와 함께 관리하는 설레연 하트 사용료.
abstract final class HeartFeatureCosts {
  static const int directChat = 10;
  static const int blindMeeting = 30;
  static const int seasonRoulette = 20;
  static const int recommendationRefresh = 5;

  /// The user-facing cost format used at every paid-feature entry point.
  static String label(int amount) => '❤️$amount';
}

class HeartEconomyService {
  HeartEconomyService({
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  }) : _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion),
       _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService();

  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;
  String? _pendingRefreshOperationId;

  /// 추천 피드 새로고침 사용료를 멱등성 키와 함께 차감한다.
  Future<int> spendForRecommendationRefresh() async {
    final userId = await _storageService.getKakaoUserId();
    if (userId == null || userId.isEmpty) {
      throw StateError('로그인이 필요해요.');
    }
    final ready = await _authService.ensureFirebaseSessionForKakao(userId);
    if (!ready) throw StateError('로그인 세션을 준비하지 못했어요.');

    final operationId = _pendingRefreshOperationId ?? const Uuid().v4();
    _pendingRefreshOperationId = operationId;
    final response = await _functions
        .httpsCallable('spendHearts')
        .call<dynamic>({
          'feature': 'recommendation_refresh',
          'operationId': operationId,
        });
    final data = response.data;
    if (data is! Map || data['heartBalance'] is! num) {
      throw StateError('하트 차감 결과를 확인하지 못했어요.');
    }
    _pendingRefreshOperationId = null;
    return (data['heartBalance'] as num).toInt();
  }
}
