// =============================================================================
// 약관 상세 바텀시트
// 경로: lib/shared/widgets/bottom_sheets/terms_detail_sheet.dart
//
// 사용 예시:
// TermsDetailSheet.show(
//   context,
//   title: '서비스 이용약관',
//   sections: [...],
//   onAgree: () => print('동의'),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _SheetColors {
  static const Color primary = Color(0xFFEF3994);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF111827);
  static const Color textBody = Color(0xFF4B5563);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
}

// =============================================================================
// 약관 섹션 데이터 모델
// =============================================================================
class TermsSection {
  final String title;
  final String content;

  const TermsSection({required this.title, required this.content});
}

// =============================================================================
// 약관 상세 바텀시트
// =============================================================================
class TermsDetailSheet extends StatelessWidget {
  final String title;
  final List<TermsSection> sections;
  final VoidCallback? onAgree;
  final String agreeButtonText;

  const TermsDetailSheet({
    super.key,
    required this.title,
    required this.sections,
    this.onAgree,
    this.agreeButtonText = '동의하기',
  });

  /// 바텀시트 표시
  static Future<bool?> show(
    BuildContext context, {
    required String title,
    required List<TermsSection> sections,
    VoidCallback? onAgree,
    String agreeButtonText = '동의하기',
  }) {
    return showCupertinoModalPopup<bool>(
      context: context,
      barrierDismissible: true,
      builder: (context) => TermsDetailSheet(
        title: title,
        sections: sections,
        onAgree: onAgree,
        agreeButtonText: agreeButtonText,
      ),
    );
  }

  void _onAgreePressed(BuildContext context) {
    HapticFeedback.mediumImpact();
    onAgree?.call();
    Navigator.of(context).pop(true);
  }

  void _onClosePressed(BuildContext context) {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop(false);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.85,
      ),
      decoration: const BoxDecoration(
        color: _SheetColors.surfaceLight,
        borderRadius: BorderRadius.vertical(top: Radius.circular(32)),
        boxShadow: [
          BoxShadow(
            color: Color(0x1A000000),
            blurRadius: 30,
            offset: Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 드래그 핸들
          const _DragHandle(),
          // 헤더
          _Header(title: title, onClose: () => _onClosePressed(context)),
          // 스크롤 가능한 컨텐츠
          Flexible(child: _ContentBody(sections: sections)),
          // 하단 동의 버튼
          _AgreeButton(
            text: agreeButtonText,
            bottomPadding: bottomPadding,
            onPressed: () => _onAgreePressed(context),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 드래그 핸들
// =============================================================================
class _DragHandle extends StatelessWidget {
  const _DragHandle();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Container(
        width: 48,
        height: 5,
        decoration: BoxDecoration(
          color: _SheetColors.gray200,
          borderRadius: BorderRadius.circular(3),
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final String title;
  final VoidCallback onClose;

  const _Header({required this.title, required this.onClose});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: _SheetColors.gray100, width: 1),
        ),
      ),
      child: Row(
        children: [
          // 좌측 여백 (균형용)
          const SizedBox(width: 40),
          // 제목
          Expanded(
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _SheetColors.textMain,
                letterSpacing: -0.3,
              ),
            ),
          ),
          // 닫기 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onClose,
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _SheetColors.gray50,
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                CupertinoIcons.xmark,
                size: 18,
                color: _SheetColors.textBody,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 컨텐츠 바디
// =============================================================================
class _ContentBody extends StatelessWidget {
  final List<TermsSection> sections;

  const _ContentBody({required this.sections});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: sections.asMap().entries.map((entry) {
          final index = entry.key;
          final section = entry.value;
          final isLast = index == sections.length - 1;

          return Padding(
            padding: EdgeInsets.only(bottom: isLast ? 16 : 24),
            child: _SectionBlock(section: section),
          );
        }).toList(),
      ),
    );
  }
}

// =============================================================================
// 섹션 블록
// =============================================================================
class _SectionBlock extends StatelessWidget {
  final TermsSection section;

  const _SectionBlock({required this.section});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          section.title,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: _SheetColors.textMain,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          section.content,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 15,
            fontWeight: FontWeight.w400,
            color: _SheetColors.textBody,
            height: 1.6,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 동의 버튼
// =============================================================================
class _AgreeButton extends StatelessWidget {
  final String text;
  final double bottomPadding;
  final VoidCallback onPressed;

  const _AgreeButton({
    required this.text,
    required this.bottomPadding,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 12, 16, bottomPadding + 16),
      decoration: BoxDecoration(
        color: _SheetColors.surfaceLight.withValues(alpha: 0.97),
        border: const Border(
          top: BorderSide(color: _SheetColors.gray100, width: 1),
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: _SheetColors.primary,
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: _SheetColors.primary.withValues(alpha: 0.35),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Center(
            child: Text(
              text,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: CupertinoColors.white,
                letterSpacing: 0.5,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 서비스 이용약관 기본 데이터 (편의용)
// =============================================================================
class DefaultTermsSections {
  static const List<TermsSection> serviceTerms = [
    TermsSection(
      title: '제1조 (목적)',
      content:
          '본 약관은 회사가 제공하는 위치기반 서비스와 관련하여 회사와 개인위치정보주체와의 권리, 의무 및 책임사항, 기타 필요한 사항을 규정함을 목적으로 합니다. 회사는 개인정보보호법 등 관련 법령을 준수하며, 이용자의 개인정보 보호를 위해 최선을 다하고 있습니다.',
    ),
    TermsSection(
      title: '제2조 (이용약관의 효력 및 변경)',
      content:
          '본 약관은 서비스를 신청한 고객 또는 개인위치정보주체가 본 약관에 동의하고 회사가 정한 소정의 절차에 따라 서비스의 이용자로 등록함으로써 효력이 발생합니다. 회사는 관련 법령을 위배하지 않는 범위에서 본 약관을 개정할 수 있습니다. 변경된 약관은 공지사항을 통해 공지하며, 효력 발생일 7일 전부터 공지합니다.',
    ),
    TermsSection(
      title: '제3조 (서비스의 내용)',
      content:
          '회사는 위치정보사업자로부터 위치정보를 전달받아 아래와 같은 위치기반서비스를 제공합니다.\n1. 접속 위치 기반 매칭 추천 서비스\n2. 현재 위치 주변의 친구 찾기 서비스\n3. 위치 기반 커뮤니티 게시글 열람 서비스',
    ),
    TermsSection(
      title: '제4조 (서비스 이용요금)',
      content:
          '회사가 제공하는 서비스는 기본적으로 무료입니다. 다만, 별도의 유료 서비스의 경우 해당 서비스에 명시된 요금을 지불하여야 사용 가능합니다. 유료 서비스의 환불 및 취소에 관한 규정은 별도의 유료 서비스 약관을 따릅니다.',
    ),
    TermsSection(
      title: '제5조 (개인위치정보의 이용 또는 제공)',
      content:
          '회사는 개인위치정보를 이용하여 서비스를 제공하고자 하는 경우에는 미리 이용약관에 명시한 후 개인위치정보주체의 동의를 얻어야 합니다. 회사는 타사업자 또는 이용 고객과의 요금정산 및 민원처리를 위해 위치정보 이용·제공사실 확인자료를 자동 기록·보존하며, 해당 자료는 1년간 보관합니다.',
    ),
  ];

  static const List<TermsSection> privacyPolicy = [
    TermsSection(
      title: '제1조 (개인정보의 수집항목)',
      content:
          '회사는 서비스 제공을 위해 다음과 같은 개인정보를 수집합니다.\n• 필수항목: 이름, 생년월일, 성별, 휴대폰번호\n• 선택항목: 프로필 사진, 학교, 학과, 관심사',
    ),
    TermsSection(
      title: '제2조 (개인정보의 이용목적)',
      content:
          '수집한 개인정보는 다음의 목적으로 이용됩니다.\n• 회원 가입 및 관리\n• 매칭 서비스 제공\n• 서비스 개선 및 신규 서비스 개발\n• 불법 이용 방지',
    ),
    TermsSection(
      title: '제3조 (개인정보의 보유 및 이용기간)',
      content:
          '회사는 개인정보 수집 및 이용목적이 달성된 후에는 해당 정보를 지체 없이 파기합니다. 단, 관련 법령에 의거하여 보존할 필요가 있는 경우 일정 기간 보관합니다.',
    ),
  ];
}
