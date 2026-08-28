import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';

import 'heart_products.dart';
import 'heart_purchase_gateway.dart';

/// UI와 플랫폼 IAP purchaseStream을 분리한 앱 수명 주기의 IAP 서비스입니다.
/// 화면을 다시 열어도 listener가 중복 생성되지 않고, 앱 재시작 시 미완료
/// transaction도 같은 idempotent 서버 경로로 처리합니다.
class IapService extends ChangeNotifier {
  IapService._({
    InAppPurchase? inAppPurchase,
    HeartPurchaseGateway? purchaseGateway,
  }) : _inAppPurchase = inAppPurchase ?? InAppPurchase.instance,
       _purchaseGateway = purchaseGateway ?? HeartPurchaseGateway();

  static final IapService instance = IapService._();

  final InAppPurchase _inAppPurchase;
  final HeartPurchaseGateway _purchaseGateway;
  final Set<String> _processingTransactionIds = <String>{};
  final Set<String> _handledTransactionIds = <String>{};

  StreamSubscription<List<PurchaseDetails>>? _purchaseSubscription;
  Future<void>? _initializeFuture;
  Future<void>? _googlePlayRestoreFuture;
  Future<void> _purchaseQueue = Future<void>.value();

  bool _isStoreAvailable = false;
  bool _isLoadingProducts = false;
  String? _activeProductId;
  String? _lastError;
  String? _lastSuccessProductId;
  List<ProductDetails> _products = const <ProductDetails>[];
  Set<String> _notFoundProductIds = const <String>{};

  HeartPurchasePlatform? get platform {
    if (kIsWeb) return null;
    return switch (defaultTargetPlatform) {
      TargetPlatform.iOS => HeartPurchasePlatform.ios,
      TargetPlatform.android => HeartPurchasePlatform.android,
      _ => null,
    };
  }

  bool get supportsIap => platform != null;
  bool get supportsAppleIap => platform == HeartPurchasePlatform.ios;
  bool get supportsGooglePlayIap => platform == HeartPurchasePlatform.android;
  String get storeName => supportsGooglePlayIap ? 'Google Play' : 'Apple';
  bool get isStoreAvailable => _isStoreAvailable;
  bool get isLoadingProducts => _isLoadingProducts;
  bool get isPurchaseInProgress => _activeProductId != null;
  String? get activeProductId => _activeProductId;
  String? get lastError => _lastError;
  String? get lastSuccessProductId => _lastSuccessProductId;
  List<ProductDetails> get products =>
      List<ProductDetails>.unmodifiable(_products);
  Set<String> get notFoundProductIds =>
      Set<String>.unmodifiable(_notFoundProductIds);

  Future<void> initialize() {
    return _initializeFuture ??= _initialize();
  }

  Future<void> _initialize() async {
    if (!supportsIap) return;

    _purchaseSubscription ??= _inAppPurchase.purchaseStream.listen(
      _onPurchaseUpdates,
      onError: (Object error, StackTrace stackTrace) {
        _recordError('구매 상태를 확인하지 못했어요. 잠시 후 다시 시도해주세요.');
        _debugLog('purchaseStream error: $error');
      },
      onDone: () {
        _debugLog('purchaseStream closed');
      },
    );

    _isStoreAvailable = await _inAppPurchase.isAvailable();
    _debugLog('${platform!.name} store available=$_isStoreAvailable');
    if (_isStoreAvailable) {
      await loadProducts();
      if (supportsGooglePlayIap) {
        // A purchase can outlive the app process (for example, if the app is
        // killed after Play confirms payment but before the backend consumes
        // the token). Query owned purchases explicitly; purchaseStream alone
        // only guarantees live BillingClient updates.
        await _restorePendingGooglePlayPurchases(showUserError: false);
      }
    } else {
      _recordError('현재 기기에서는 $storeName 결제를 사용할 수 없어요.');
    }
    notifyListeners();
  }

  /// Re-queries unconsumed Google Play purchases and sends them through the
  /// same idempotent server verification path as a live purchase update.
  ///
  /// The heart screen calls this after loading the signed-in Kakao account so
  /// a purchase that could not be granted during logged-out app startup gets a
  /// deterministic retry without asking the user to pay again.
  Future<void> restorePendingPurchases() async {
    await initialize();
    if (!supportsGooglePlayIap || !_isStoreAvailable) return;
    await _restorePendingGooglePlayPurchases(showUserError: true);
  }

  Future<void> _restorePendingGooglePlayPurchases({
    required bool showUserError,
  }) {
    final inFlight = _googlePlayRestoreFuture;
    if (inFlight != null) return inFlight;

    final restore = () async {
      try {
        _debugLog('Querying unconsumed Google Play purchases');
        await _inAppPurchase.restorePurchases();
      } catch (error) {
        if (showUserError) {
          _recordError('이전에 완료되지 않은 결제 내역을 확인하지 못했어요. 다시 시도해주세요.');
        }
        _debugLog('Google Play pending purchase query failed: $error');
      }
    }();
    _googlePlayRestoreFuture = restore;
    return restore.whenComplete(() {
      if (identical(_googlePlayRestoreFuture, restore)) {
        _googlePlayRestoreFuture = null;
      }
    });
  }

  Future<void> loadProducts() async {
    final purchasePlatform = platform;
    if (purchasePlatform == null || !_isStoreAvailable) return;

    _isLoadingProducts = true;
    _lastError = null;
    notifyListeners();
    try {
      final response = await _inAppPurchase.queryProductDetails(
        HeartProducts.productIdsFor(purchasePlatform),
      );
      _notFoundProductIds = response.notFoundIDs.toSet();
      if (response.error != null) {
        _products = const <ProductDetails>[];
        _recordError('하트 상품을 불러오지 못했어요. 다시 시도해주세요.');
        _debugLog('Product query error: ${response.error}');
        return;
      }

      final byId = <String, ProductDetails>{
        for (final product in response.productDetails) product.id: product,
      };
      _products = HeartProducts.productsFor(purchasePlatform)
          .map(
            (heartProduct) => byId[heartProduct.productIdFor(purchasePlatform)],
          )
          .whereType<ProductDetails>()
          .toList(growable: false);
      _debugLog(
        'Products loaded=${_products.length}, missing=${_notFoundProductIds.length}',
      );
      if (_products.isEmpty) {
        _recordError('구매 가능한 하트 상품을 찾지 못했어요.');
      }
    } catch (error) {
      _products = const <ProductDetails>[];
      _recordError('하트 상품을 불러오지 못했어요. 다시 시도해주세요.');
      _debugLog('Product query exception: $error');
    } finally {
      _isLoadingProducts = false;
      notifyListeners();
    }
  }

  Future<void> buy(ProductDetails product) async {
    await initialize();
    final purchasePlatform = platform;
    if (!_isStoreAvailable || purchasePlatform == null) {
      _recordError('$storeName 결제를 사용할 수 없어요.');
      return;
    }
    if (_activeProductId != null) return;
    if (HeartProducts.fromProductId(product.id, platform: purchasePlatform) ==
        null) {
      _recordError('지원하지 않는 하트 상품이에요.');
      return;
    }

    _activeProductId = product.id;
    _lastError = null;
    _lastSuccessProductId = null;
    notifyListeners();
    _debugLog(
      '${purchasePlatform.name} purchase requested product=${product.id}',
    );

    try {
      final purchaseParam = supportsGooglePlayIap
          ? GooglePlayPurchaseParam(
              productDetails: product,
              applicationUserName: await _purchaseGateway
                  .prepareGooglePlayAccountId(),
            )
          : PurchaseParam(productDetails: product);
      final started = await _inAppPurchase.buyConsumable(
        purchaseParam: purchaseParam,
        // Android는 서버 지급이 성공한 뒤 명시적으로 consume한다. 기본값 true는
        // purchaseStream listener보다 먼저 token을 소비할 수 있다.
        autoConsume: !supportsGooglePlayIap,
      );
      if (!started) {
        _activeProductId = null;
        _recordError('구매를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
      }
    } catch (error) {
      _activeProductId = null;
      _recordError('구매를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
      _debugLog('Purchase request exception: $error');
    }
  }

  void _onPurchaseUpdates(List<PurchaseDetails> purchases) {
    // 각 batch와 재전달 이벤트를 직렬 처리해 같은 transaction의 동시 지급을 막는다.
    _purchaseQueue = _purchaseQueue
        .then((_) async {
          for (final purchase in purchases) {
            await _handlePurchase(purchase);
          }
        })
        .catchError((Object error) {
          _recordError('구매 상태를 처리하지 못했어요. 앱을 다시 열어주세요.');
          _debugLog('Purchase queue exception: $error');
        });
  }

  Future<void> _handlePurchase(PurchaseDetails purchase) async {
    switch (purchase.status) {
      case PurchaseStatus.pending:
        _activeProductId = purchase.productID;
        _lastError = null;
        _debugLog('Purchase pending product=${purchase.productID}');
        notifyListeners();
        return;
      case PurchaseStatus.purchased:
      case PurchaseStatus.restored:
        await _verifyGrantAndComplete(purchase);
        return;
      case PurchaseStatus.canceled:
        _activeProductId = null;
        _lastError = null;
        _debugLog('Purchase canceled product=${purchase.productID}');
        notifyListeners();
        return;
      case PurchaseStatus.error:
        _activeProductId = null;
        _recordError('결제가 완료되지 않았어요. 하트는 지급되지 않았습니다.');
        _debugLog(
          'Purchase error product=${purchase.productID}: ${purchase.error}',
        );
        return;
    }
  }

  Future<void> _verifyGrantAndComplete(PurchaseDetails purchase) async {
    final purchasePlatform = platform;
    if (purchasePlatform == null) return;
    final heartProduct = HeartProducts.fromProductId(
      purchase.productID,
      platform: purchasePlatform,
    );
    if (heartProduct == null) {
      _activeProductId = null;
      _recordError('확인할 수 없는 구매 상품이에요.');
      return;
    }

    final transactionId = _transactionIdFor(purchase);
    _debugLog(
      '[${purchasePlatform.name.toUpperCase()}] purchase received '
      'status=${purchase.status.name} product=${purchase.productID} '
      'transaction=${_logKey(transactionId)}',
    );
    if (_handledTransactionIds.contains(transactionId)) {
      // 같은 이벤트가 completePurchase 직후 다시 도착할 수 있다. 이미 서버 지급은
      // 끝났으므로 이 경우에는 지급을 반복하지 않고 소비/마무리만 재시도한다.
      if (purchase.pendingCompletePurchase) {
        await _completePurchase(purchase, transactionId);
      }
      return;
    }
    if (!_processingTransactionIds.add(transactionId)) {
      _debugLog(
        'Duplicate delivery ignored transaction=${_logKey(transactionId)}',
      );
      return;
    }

    var granted = false;
    try {
      final verificationData = _verificationDataFor(purchase);
      _debugLog(
        '[${purchasePlatform.name.toUpperCase()}] verification and heart grant started '
        'transaction=${_logKey(transactionId)}',
      );
      final result = await _purchaseGateway.grantPurchasedHearts(
        productId: purchase.productID,
        platform: purchasePlatform,
        transactionId: transactionId,
        verificationData: verificationData,
        verificationSource: purchase.verificationData.source,
        purchaseDate: purchase.transactionDate,
      );
      granted = true;
      _debugLog(
        '${purchasePlatform.name} purchase verified transaction=${_logKey(transactionId)} granted=${result.granted} '
        'alreadyGranted=${result.alreadyGranted} balance=${result.heartBalance}',
      );

      _debugLog(
        '[${purchasePlatform.name.toUpperCase()}] entitlement recorded; '
        'completing purchase transaction=${_logKey(transactionId)}',
      );
      await _completePurchase(purchase, transactionId);

      _handledTransactionIds.add(transactionId);
      _activeProductId = null;
      _lastError = null;
      _lastSuccessProductId = purchase.productID;
      notifyListeners();
    } catch (error) {
      _activeProductId = null;
      _recordError(
        granted
            ? '하트는 지급됐지만 결제 마무리를 확인하지 못했어요. 앱을 다시 열어주세요.'
            : '결제 처리 상태를 확인 중이에요. 하트가 보이지 않으면 앱을 다시 열어주세요.',
      );
      _debugLog(
        'Purchase processing failed transaction=${_logKey(transactionId)}: $error',
      );
    } finally {
      _processingTransactionIds.remove(transactionId);
    }
  }

  String _verificationDataFor(PurchaseDetails purchase) {
    final serverData = purchase.verificationData.serverVerificationData.trim();
    if (serverData.isNotEmpty) return serverData;
    return purchase.verificationData.localVerificationData.trim();
  }

  String _transactionIdFor(PurchaseDetails purchase) {
    // Google Play의 orderId는 한 주문에 여러 상품이 포함될 수 있고 nullable이다.
    // 서버 idempotency key는 재전달에도 변하지 않는 purchaseToken을 사용한다.
    if (supportsGooglePlayIap) {
      final token = purchase.verificationData.serverVerificationData.trim();
      if (token.isNotEmpty) return token;
    }
    final purchaseId = purchase.purchaseID?.trim();
    if (purchaseId != null && purchaseId.isNotEmpty) return purchaseId;

    // purchaseID가 비어 있는 플랫폼 예외에서도 동일 receipt 재전달을 같은
    // transaction으로 식별한다. 원문 receipt는 로컬에 저장하거나 로그에 남기지 않는다.
    final fingerprint = sha256.convert(
      utf8.encode('${purchase.productID}:${_verificationDataFor(purchase)}'),
    );
    return 'receipt-$fingerprint';
  }

  Future<void> _completePurchase(
    PurchaseDetails purchase,
    String transactionId,
  ) async {
    if (supportsGooglePlayIap) {
      // Google Play products are consumed by the verified backend callable.
      _debugLog(
        'android purchase completed by backend transaction=${_logKey(transactionId)}',
      );
      return;
    }

    // StoreKit transaction is completed only after the server grants hearts.
    if (purchase.pendingCompletePurchase && !supportsGooglePlayIap) {
      _debugLog(
        '[IOS] completing StoreKit transaction=${_logKey(transactionId)}',
      );
      await _inAppPurchase.completePurchase(purchase);
      _debugLog(
        '[IOS] StoreKit transaction completed=${_logKey(transactionId)}',
      );
    }
  }

  String _logKey(String transactionId) =>
      sha256.convert(utf8.encode(transactionId)).toString().substring(0, 12);

  void _recordError(String message) {
    _lastError = message;
    notifyListeners();
  }

  void _debugLog(String message) {
    if (kDebugMode) debugPrint('[IAP] $message');
  }

  @override
  void dispose() {
    _purchaseSubscription?.cancel();
    _purchaseSubscription = null;
    super.dispose();
  }
}
