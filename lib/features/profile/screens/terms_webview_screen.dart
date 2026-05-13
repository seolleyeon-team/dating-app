// =============================================================================
// 약관 보기 화면
// 기존 RouteNames.termsWebview 라우트를 유지하면서 앱 내부 약관 목록을 표시한다.
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Brightness, Theme;
import 'package:flutter/services.dart';

import '../../../constants/legal_texts.dart';
import '../../../core/constants/app_colors.dart';
import '../../onboarding/screens/terms_detail_sheet.dart';

class TermsWebViewScreen extends StatelessWidget {
  const TermsWebViewScreen({super.key});

  List<TermsSection> _sheetSectionsFor(LegalTextDocument document) {
    return document.sections
        .map(
          (section) =>
              TermsSection(title: section.title, content: section.content),
        )
        .toList();
  }

  Future<void> _showDocument(
    BuildContext context,
    LegalTextDocument document,
  ) async {
    HapticFeedback.selectionClick();
    await TermsDetailSheet.show(
      context,
      title: document.title,
      sections: _sheetSectionsFor(document),
      agreeButtonText: '확인',
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? AppColorsDark.background : const Color(0xFFF8F6F6);
    final surfaceColor = isDark ? AppColorsDark.surface : CupertinoColors.white;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final textSub = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF89616B);
    final divider = isDark ? AppColorsDark.divider : const Color(0xFFF3E8ED);
    final primary = Theme.of(context).colorScheme.primary;

    return CupertinoPageScaffold(
      backgroundColor: bgColor,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: surfaceColor.withValues(alpha: 0.86),
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pop();
          },
          child: Icon(CupertinoIcons.back, color: textMain),
        ),
        middle: Text(
          '약관 보기',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 48),
          children: [
            Container(
              padding: const EdgeInsets.all(22),
              decoration: BoxDecoration(
                color: primary.withValues(alpha: isDark ? 0.12 : 0.08),
                borderRadius: BorderRadius.circular(28),
                border: Border.all(
                  color: primary.withValues(alpha: isDark ? 0.16 : 0.12),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '설레연 약관 및 개인정보 안내',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 21,
                      fontWeight: FontWeight.w800,
                      height: 1.35,
                      color: textMain,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '서비스 이용약관, 개인정보 처리방침, 카카오 이름 및 전화번호 수집·이용 동의 내용을 확인할 수 있어요.',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      height: 1.55,
                      color: textSub,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Container(
              decoration: BoxDecoration(
                color: surfaceColor,
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: divider),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(
                      alpha: isDark ? 0.12 : 0.03,
                    ),
                    blurRadius: 20,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Column(
                children: [
                  for (final entry in LegalTexts.documents.asMap().entries) ...[
                    _LegalDocumentRow(
                      document: entry.value,
                      textMain: textMain,
                      textSub: textSub,
                      primary: primary,
                      onTap: () => _showDocument(context, entry.value),
                    ),
                    if (entry.key != LegalTexts.documents.length - 1)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        child: Container(height: 1, color: divider),
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LegalDocumentRow extends StatelessWidget {
  final LegalTextDocument document;
  final Color textMain;
  final Color textSub;
  final Color primary;
  final VoidCallback onTap;

  const _LegalDocumentRow({
    required this.document,
    required this.textMain,
    required this.textSub,
    required this.primary,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: primary.withValues(alpha: 0.08),
                shape: BoxShape.circle,
              ),
              child: Icon(CupertinoIcons.doc_text, size: 22, color: primary),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    document.title,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: textMain,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    document.summary,
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      height: 1.35,
                      color: textSub,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Icon(
              CupertinoIcons.chevron_right,
              size: 18,
              color: textSub.withValues(alpha: 0.55),
            ),
          ],
        ),
      ),
    );
  }
}
