import 'package:flutter/cupertino.dart';

import '../../../constants/app_constants.dart';

/// 3:3 시즌 미팅의 상품, 예치금, 참여 규정 및 사업자 안내를 한 곳에 모은 화면.
///
/// 결제대행사 심사와 실제 결제 오픈 전에 고객이 확인할 정보를 명확히
/// 고지하기 위한 화면이다.
class SeasonMeetingPaymentGuideScreen extends StatelessWidget {
  const SeasonMeetingPaymentGuideScreen({super.key});

  static const _merchant = _MerchantInfo.seolleyeon();

  @override
  Widget build(BuildContext context) {
    final primary = CupertinoTheme.of(context).primaryColor;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFDF9FA),
      navigationBar: CupertinoNavigationBar(
        middle: const Text('3:3 시즌 미팅 안내'),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: const Icon(CupertinoIcons.back),
        ),
      ),
      child: SafeArea(
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
          children: [
            _Hero(primary: primary),
            const SizedBox(height: 16),
            const _SectionTitle('판매 상품 및 상세'),
            _SurfaceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      _CircleIcon(
                        icon: CupertinoIcons.person_3_fill,
                        color: primary,
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '3:3 시즌 미팅 참여 보증금',
                              style: TextStyle(
                                fontSize: 17,
                                fontWeight: FontWeight.w700,
                                color: _GuideColors.ink,
                              ),
                            ),
                            SizedBox(height: 3),
                            Text(
                              '매칭 수락 후 1인당 결제',
                              style: TextStyle(
                                fontSize: 13,
                                color: _GuideColors.sub,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        '${AppConstants.meetingDeposit.toString()}원',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          color: primary,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  const _RuleRow(
                    label: '제공 서비스',
                    value: '검증된 회원 6명의 3:3 시즌 미팅 매칭 및 단체 채팅방 이용',
                  ),
                  const _RuleRow(
                    label: '서비스 제공 시점',
                    value: '참가자 전원의 예치금 결제가 확인되면 단체 채팅방이 열립니다.',
                  ),
                  const _RuleRow(
                    label: '배송 여부',
                    value: '배송 상품이 아닌 디지털 미팅 서비스입니다.',
                    isLast: true,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const _SectionTitle('서비스 이용 안내'),
            _SurfaceCard(
              child: const Column(
                children: [
                  _FlowStep(
                    number: '1',
                    title: '팀 만들기',
                    description: '친구와 3인 팀을 구성해 시즌 미팅에 참여해요.',
                  ),
                  _FlowStep(
                    number: '2',
                    title: '상대 팀 매칭 및 수락',
                    description: '상대 팀을 확인한 뒤 양쪽 팀이 미팅을 수락해요.',
                  ),
                  _FlowStep(
                    number: '3',
                    title: '예치금 결제',
                    description: '참가자 모두의 결제가 확인되면 미팅이 확정돼요.',
                  ),
                  _FlowStep(
                    number: '4',
                    title: '3:3 단체 채팅 시작',
                    description: '열린 채팅방에서 시간과 장소를 정해요.',
                    isLast: true,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const _SectionTitle('예치금 및 불참·대타 규정'),
            _SurfaceCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '예치금은 참여 확정 뒤의 불참·취소를 줄이고 안전한 만남을 만들기 위한 보증금입니다.',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: _GuideColors.ink,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 16),
                  _RefundRule(
                    title: '참여 확정 후 불참 또는 참여 취소',
                    detail: '예치금은 환급되지 않습니다.',
                    color: primary,
                  ),
                  const _RefundRule(
                    title: '참석이 어려운 경우',
                    detail: '본인이 대체 참가자(대타)를 반드시 구해야 합니다.',
                  ),
                  const _RefundRule(
                    title: '대타를 구하는 동안',
                    detail: '본인의 참가 의무와 대타 섭외 책임은 유지됩니다.',
                  ),
                  const _RefundRule(
                    title: '무단 불참',
                    detail: '예치금은 환급되지 않으며 서비스 이용이 제한될 수 있습니다.',
                    isLast: true,
                  ),
                  const SizedBox(height: 14),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF4F6),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: const Text(
                      '상대 팀과의 약속을 지키기 위한 정책입니다. 참여 의사를 확정하기 전, 참석 가능 여부를 꼭 확인해주세요.',
                      style: TextStyle(
                        fontSize: 13,
                        color: _GuideColors.sub,
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const _SectionTitle('사업자 및 고객 문의'),
            _SurfaceCard(
              child: Column(
                children: [
                  _MerchantRow(label: '서비스명', value: _merchant.serviceName),
                  _MerchantRow(label: '상호', value: _merchant.legalName),
                  _MerchantRow(label: '대표자명', value: _merchant.representative),
                  _MerchantRow(
                    label: '사업자등록번호',
                    value: _merchant.businessRegistrationNumber,
                  ),
                  _MerchantRow(
                    label: '통신판매업 신고번호',
                    value: _merchant.mailOrderRegistrationNumber,
                  ),
                  _MerchantRow(label: '사업장 주소', value: _merchant.address),
                  _MerchantRow(label: '연락처', value: _merchant.supportPhone),
                  _MerchantRow(
                    label: '고객 문의 이메일',
                    value: _merchant.supportEmail,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text(
              '결제수단과 전자결제대행사 연동은 계약 및 기술 연동이 완료된 뒤 제공됩니다. 결제 오픈 전에는 실제 결제가 진행되지 않습니다.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 12,
                color: _GuideColors.sub,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MerchantInfo {
  final String serviceName;
  final String legalName;
  final String representative;
  final String businessRegistrationNumber;
  final String mailOrderRegistrationNumber;
  final String address;
  final String supportPhone;
  final String supportEmail;

  const _MerchantInfo({
    required this.serviceName,
    required this.legalName,
    required this.representative,
    required this.businessRegistrationNumber,
    required this.mailOrderRegistrationNumber,
    required this.address,
    required this.supportPhone,
    required this.supportEmail,
  });

  const _MerchantInfo.seolleyeon()
    : serviceName = '설레연',
      legalName = '설레연',
      representative = '임채홍',
      businessRegistrationNumber = '120-35-01737 (간이과세자)',
      mailOrderRegistrationNumber = '2026-제주애월-0146',
      address = '제주특별자치도 제주시 애월읍 납읍로2길 68 1층',
      supportPhone = '010-7435-1916',
      supportEmail = 'seolleyeon.official@gmail.com';
}

class _GuideColors {
  static const ink = Color(0xFF20191B);
  static const sub = Color(0xFF75666B);
}

class _Hero extends StatelessWidget {
  final Color primary;

  const _Hero({required this.primary});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [primary, const Color(0xFFFF8EA5)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            CupertinoIcons.shield_lefthalf_fill,
            color: CupertinoColors.white,
          ),
          SizedBox(height: 14),
          Text(
            '안전한 3:3 시즌 미팅을 위한\n결제·이용 안내',
            style: TextStyle(
              color: CupertinoColors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              height: 1.3,
            ),
          ),
          SizedBox(height: 8),
          Text(
            '참여 전 예치금, 서비스 제공 시점, 불참·대타 규정을 확인해주세요.',
            style: TextStyle(
              color: CupertinoColors.white,
              fontSize: 13,
              height: 1.45,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 4, bottom: 9),
    child: Text(
      text,
      style: const TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w800,
        color: _GuideColors.ink,
      ),
    ),
  );
}

class _SurfaceCard extends StatelessWidget {
  final Widget child;

  const _SurfaceCard({required this.child});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: CupertinoColors.white,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: const Color(0xFFF1E7EA)),
    ),
    child: child,
  );
}

class _CircleIcon extends StatelessWidget {
  final IconData icon;
  final Color color;

  const _CircleIcon({required this.icon, required this.color});

  @override
  Widget build(BuildContext context) => Container(
    width: 42,
    height: 42,
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.12),
      shape: BoxShape.circle,
    ),
    child: Icon(icon, color: color, size: 21),
  );
}

class _RuleRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isLast;

  const _RuleRow({
    required this.label,
    required this.value,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(vertical: 11),
    decoration: BoxDecoration(
      border: isLast
          ? null
          : const Border(bottom: BorderSide(color: Color(0xFFF3ECEE))),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 96,
          child: Text(
            label,
            style: const TextStyle(fontSize: 13, color: _GuideColors.sub),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              color: _GuideColors.ink,
              height: 1.45,
            ),
          ),
        ),
      ],
    ),
  );
}

class _FlowStep extends StatelessWidget {
  final String number;
  final String title;
  final String description;
  final bool isLast;

  const _FlowStep({
    required this.number,
    required this.title,
    required this.description,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final primary = CupertinoTheme.of(context).primaryColor;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: primary, shape: BoxShape.circle),
              child: Text(
                number,
                style: const TextStyle(
                  color: CupertinoColors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            if (!isLast)
              Container(width: 1, height: 38, color: const Color(0xFFF0DCE1)),
          ],
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: isLast ? 0 : 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: _GuideColors.ink,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  description,
                  style: const TextStyle(
                    fontSize: 13,
                    color: _GuideColors.sub,
                    height: 1.45,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _RefundRule extends StatelessWidget {
  final String title;
  final String detail;
  final Color? color;
  final bool isLast;

  const _RefundRule({
    required this.title,
    required this.detail,
    this.color,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(vertical: 11),
    decoration: BoxDecoration(
      border: isLast
          ? null
          : const Border(bottom: BorderSide(color: Color(0xFFF3ECEE))),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: _GuideColors.ink,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          detail,
          style: TextStyle(
            fontSize: 13,
            color: color ?? _GuideColors.sub,
            height: 1.4,
          ),
        ),
      ],
    ),
  );
}

class _MerchantRow extends StatelessWidget {
  final String label;
  final String value;

  const _MerchantRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 120,
          child: Text(
            label,
            style: const TextStyle(fontSize: 13, color: _GuideColors.sub),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              color: _GuideColors.ink,
              height: 1.4,
            ),
          ),
        ),
      ],
    ),
  );
}
