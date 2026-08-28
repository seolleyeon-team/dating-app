import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:in_app_purchase/in_app_purchase.dart';

import '../../../services/storage_service.dart';
import '../../shop/services/heart_products.dart';
import '../../shop/services/iap_service.dart';
import '../../../shared/utils/in_app_purchase_policy.dart';

class _AppColors {
  static const Color primary = Color(0xFFFF4081);
  static const Color backgroundLight = Color(0xFFF8F9FA);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textPrimary = Color(0xFF1A1A1A);
  static const Color textSecondary = Color(0xFF8E8E93);
}

/// 하트 구매 화면입니다. 플랫폼별 IAP는 IapService가 앱 단위로 관리합니다.
class HeartChargeScreen extends StatefulWidget {
  const HeartChargeScreen({super.key});

  @override
  State<HeartChargeScreen> createState() => _HeartChargeScreenState();
}

class _HeartChargeScreenState extends State<HeartChargeScreen> {
  final IapService _iapService = IapService.instance;
  final StorageService _storageService = StorageService();
  String? _kakaoUserId;

  @override
  void initState() {
    super.initState();
    unawaited(_preparePurchases());
  }

  Future<void> _preparePurchases() async {
    await _loadUser();
    await _iapService.initialize();
    await _iapService.restorePendingPurchases();
  }

  Future<void> _loadUser() async {
    final userId = await _storageService.getKakaoUserId();
    if (mounted) setState(() => _kakaoUserId = userId);
  }

  void _onBuy(ProductDetails details) {
    if (InAppPurchasePolicy.allowPurchaseUi) {
      unawaited(_iapService.buy(details));
      return;
    }
    showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('하트 충전'),
        content: Text(InAppPurchasePolicy.unavailableMessage),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        child: AnimatedBuilder(
          animation: _iapService,
          builder: (context, _) => Column(
            children: [
              _Header(onClose: () => Navigator.of(context).pop()),
              _CurrentBalance(kakaoUserId: _kakaoUserId),
              const SizedBox(height: 8),
              const _PromoBanner(),
              const SizedBox(height: 16),
              if (_iapService.lastError != null)
                _PurchaseNotice(message: _iapService.lastError!, isError: true)
              else if (_iapService.lastSuccessProductId != null)
                const _PurchaseNotice(
                  message: '하트가 성공적으로 충전됐어요.',
                  isError: false,
                ),
              Expanded(child: _buildProductBody()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildProductBody() {
    if (!_iapService.supportsIap) {
      return const _CenteredMessage(
        '하트 구매는 iPhone, iPad 또는 Android에서 이용할 수 있어요.',
      );
    }
    if (_iapService.isLoadingProducts) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (!_iapService.isStoreAvailable) {
      return _CenteredMessage('현재 ${_iapService.storeName} 결제를 사용할 수 없어요.');
    }
    if (_iapService.products.isEmpty) {
      return Center(
        child: CupertinoButton(
          onPressed: _iapService.loadProducts,
          child: const Text('상품을 다시 불러오기'),
        ),
      );
    }

    return ListView.separated(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 48),
      itemCount: _iapService.products.length + 1,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        if (index == _iapService.products.length) {
          return Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Center(
              child: Text(
                '결제는 ${_iapService.storeName}을 통해 안전하게 처리됩니다.',
                style: const TextStyle(
                  fontSize: 12,
                  color: _AppColors.textSecondary,
                ),
              ),
            ),
          );
        }
        final details = _iapService.products[index];
        final package = HeartProducts.fromProductId(
          details.id,
          platform: _iapService.platform!,
        )!;
        return _ProductCard(
          details: details,
          heartPackage: package,
          isBusy: _iapService.isPurchaseInProgress,
          isActive: _iapService.activeProductId == details.id,
          onPressed: () => _onBuy(details),
        );
      },
    );
  }
}

class _Header extends StatelessWidget {
  final VoidCallback onClose;

  const _Header({required this.onClose});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '하트 충전',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 24,
              fontWeight: FontWeight.w700,
              color: _AppColors.textPrimary,
              letterSpacing: -0.5,
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onClose,
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: const BoxDecoration(
                color: _AppColors.backgroundLight,
                shape: BoxShape.circle,
              ),
              child: const Icon(CupertinoIcons.xmark, color: Color(0xFF424242)),
            ),
          ),
        ],
      ),
    );
  }
}

class _CurrentBalance extends StatelessWidget {
  final String? kakaoUserId;

  const _CurrentBalance({required this.kakaoUserId});

  @override
  Widget build(BuildContext context) {
    final userId = kakaoUserId;
    if (userId == null || userId.isEmpty) return const _BalanceRow(balance: 0);

    return StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
      stream: FirebaseFirestore.instance
          .collection('users')
          .doc(userId)
          .snapshots(),
      builder: (context, snapshot) {
        final data = snapshot.data?.data();
        final balance = (data?['heartBalance'] as num?)?.toInt() ?? 0;
        return _BalanceRow(balance: balance);
      },
    );
  }
}

class _BalanceRow extends StatelessWidget {
  final int balance;

  const _BalanceRow({required this.balance});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '현재 보유 하트',
            style: TextStyle(
              fontSize: 14,
              color: _AppColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
          Text(
            '$balance하트',
            style: const TextStyle(
              fontSize: 14,
              color: _AppColors.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _PromoBanner extends StatelessWidget {
  const _PromoBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: const LinearGradient(
          colors: [Color(0xFFFCE4EC), Color(0xFFF3E5F5)],
        ),
      ),
      child: const Row(
        children: [
          Icon(CupertinoIcons.heart_fill, color: _AppColors.primary, size: 28),
          SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '더 많은 연결을 시작해보세요',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  '하트는 좋아요를 보내는 데 사용할 수 있어요.',
                  style: TextStyle(fontSize: 12, color: Color(0xFF616161)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PurchaseNotice extends StatelessWidget {
  final String message;
  final bool isError;

  const _PurchaseNotice({required this.message, required this.isError});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(20, 0, 20, 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isError ? const Color(0xFFFFE8EA) : const Color(0xFFE8F7EE),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        message,
        style: TextStyle(
          fontSize: 13,
          color: isError ? const Color(0xFFB3263D) : const Color(0xFF167244),
        ),
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  final ProductDetails details;
  final HeartProduct heartPackage;
  final bool isBusy;
  final bool isActive;
  final VoidCallback onPressed;

  const _ProductCard({
    required this.details,
    required this.heartPackage,
    required this.isBusy,
    required this.isActive,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(
            color: Color(0x0A000000),
            blurRadius: 8,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: const BoxDecoration(
              color: Color(0xFFFCE4EC),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              CupertinoIcons.heart_fill,
              color: _AppColors.primary,
              size: 24,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  details.title,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  details.description.isEmpty
                      ? '${heartPackage.hearts}하트'
                      : details.description,
                  style: const TextStyle(
                    fontSize: 12,
                    color: _AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          CupertinoButton(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            color: _AppColors.primary,
            disabledColor: const Color(0xFFFFB6CB),
            onPressed: isBusy ? null : onPressed,
            child: isActive
                ? const CupertinoActivityIndicator(color: CupertinoColors.white)
                : Text(
                    details.price,
                    style: const TextStyle(
                      color: CupertinoColors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _CenteredMessage extends StatelessWidget {
  final String message;

  const _CenteredMessage(this.message);

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(color: _AppColors.textSecondary),
      ),
    ),
  );
}
