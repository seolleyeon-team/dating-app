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

import '../../../constants/legal_texts.dart';

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
  static List<TermsSection> get serviceTerms =>
      _toTermsSections(LegalTexts.serviceTerms);

  static List<TermsSection> get privacyPolicy =>
      _toTermsSections(LegalTexts.privacyPolicy);

  static List<TermsSection> get kakaoNamePhoneConsent =>
      _toTermsSections(LegalTexts.kakaoNamePhoneConsent);

  static List<TermsSection> _toTermsSections(LegalTextDocument document) {
    return document.sections
        .map(
          (section) =>
              TermsSection(title: section.title, content: section.content),
        )
        .toList();
  }
}
