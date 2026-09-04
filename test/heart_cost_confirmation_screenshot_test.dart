import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/shop/widgets/heart_spend_confirmation.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await (FontLoader(
      'Pretendard',
    )..addFont(rootBundle.load('assets/fonts/PretendardVariable.ttf'))).load();
    await (FontLoader(
      'CupertinoSystemText',
    )..addFont(rootBundle.load('assets/fonts/PretendardVariable.ttf'))).load();
    await (FontLoader(
      'CupertinoSystemDisplay',
    )..addFont(rootBundle.load('assets/fonts/PretendardVariable.ttf'))).load();
    await (FontLoader(
      'NanumSquareRound',
    )..addFont(rootBundle.load('assets/fonts/NanumSquareRoundR.ttf'))).load();
    await (FontLoader(
      'MaterialIcons',
    )..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'))).load();
    await (FontLoader('packages/cupertino_icons/CupertinoIcons')..addFont(
          rootBundle.load('packages/cupertino_icons/assets/CupertinoIcons.ttf'),
        ))
        .load();
  });

  void configurePhone(WidgetTester tester) {
    tester.view.devicePixelRatio = 3;
    tester.view.physicalSize = const Size(1170, 2532);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
  }

  Future<void> capture(
    WidgetTester tester, {
    required String golden,
    required String screenTitle,
    required String action,
    required int amount,
    String? chargeMessage,
    String? detail,
  }) async {
    configurePhone(tester);
    const captureKey = Key('heart-cost-capture');
    await tester.pumpWidget(
      RepaintBoundary(
        key: captureKey,
        child: CupertinoApp(
          debugShowCheckedModeBanner: false,
          theme: const CupertinoThemeData(
            textTheme: CupertinoTextThemeData(
              textStyle: TextStyle(fontFamily: 'Pretendard'),
              actionTextStyle: TextStyle(fontFamily: 'Pretendard'),
            ),
          ),
          home: _HeartCostPreview(
            screenTitle: screenTitle,
            action: action,
            amount: amount,
            chargeMessage: chargeMessage,
            detail: detail,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 800));

    await expectLater(find.byKey(captureKey), matchesGoldenFile(golden));
  }

  testWidgets('captures blind meeting 30-heart confirmation', (tester) async {
    await capture(
      tester,
      golden: 'goldens/heart_cost_01_blind_meeting.png',
      screenTitle: '3:3 블라인드 미팅 날짜 신청',
      action: '정말로 3:3 블라인드 미팅에 참여하시겠습니까?',
      amount: 30,
      chargeMessage: '새 신청이면 하트 30개가 차감됩니다.',
      detail: '새 참가 신청일 때만 차감되며, 진행 중인 신청 수정은 무료입니다.',
    );
  });

  testWidgets('captures direct chat 10-heart confirmation', (tester) async {
    await capture(
      tester,
      golden: 'goldens/heart_cost_02_direct_chat.png',
      screenTitle: '첫 메시지 보내기',
      action: '정말로 메시지를 보내시겠습니까?',
      amount: 10,
      chargeMessage: '첫 채팅방을 열면 하트 10개가 차감됩니다.',
      detail: '첫 채팅방을 열 때만 차감되며, 이미 열린 채팅방은 무료입니다.',
    );
  });

  testWidgets('captures recommendation refresh 5-heart confirmation', (
    tester,
  ) async {
    await capture(
      tester,
      golden: 'goldens/heart_cost_03_recommendation_refresh.png',
      screenTitle: '오늘의 추천 새로고침',
      action: '정말로 추천을 새로고침하시겠습니까?',
      amount: 5,
      chargeMessage: '추천 새로고침 시 하트 5개가 차감됩니다.',
    );
  });
}

class _HeartCostPreview extends StatefulWidget {
  const _HeartCostPreview({
    required this.screenTitle,
    required this.action,
    required this.amount,
    this.chargeMessage,
    this.detail,
  });

  final String screenTitle;
  final String action;
  final int amount;
  final String? chargeMessage;
  final String? detail;

  @override
  State<_HeartCostPreview> createState() => _HeartCostPreviewState();
}

class _HeartCostPreviewState extends State<_HeartCostPreview> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      confirmHeartSpend(
        context,
        action: widget.action,
        amount: widget.amount,
        chargeMessage: widget.chargeMessage,
        detail: widget.detail,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFF8F4F6),
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          widget.screenTitle,
          style: const TextStyle(fontFamily: 'Pretendard'),
        ),
      ),
      child: SafeArea(
        child: Center(
          child: Container(
            margin: const EdgeInsets.all(28),
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: CupertinoColors.white,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              widget.screenTitle,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 20,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
