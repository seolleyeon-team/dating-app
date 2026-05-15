import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Brightness, Theme;

import '../../../core/constants/app_colors.dart';

class FaqScreen extends StatelessWidget {
  const FaqScreen({super.key});

  static const _items = <_FaqItem>[
    _FaqItem(
      question: '설레연은 어떤 서비스인가요?',
      answer:
          '설레연은 연세대학교 학생 인증을 기반으로 한 매칭 커뮤니티입니다. 프로필, 취향, 생활권 정보를 바탕으로 새로운 사람을 더 안전하게 만날 수 있도록 돕습니다.',
    ),
    _FaqItem(
      question: '학생 인증은 왜 필요한가요?',
      answer:
          '실사용자 확인과 안전한 커뮤니티 운영을 위해 연세 메일 인증을 사용합니다. 인증 정보는 서비스 이용 자격 확인과 악성 이용 방지 목적으로만 활용됩니다.',
    ),
    _FaqItem(
      question: '이름과 전화번호는 어디에 사용되나요?',
      answer:
          '카카오 로그인 과정에서 제공받을 수 있는 이름과 전화번호는 실사용자 확인, 중복 가입 방지, 신고·차단·제재 대응 등 안전 관리 목적으로 사용됩니다.',
    ),
    _FaqItem(
      question: '학과나 RA 여부가 다른 사람에게 보이나요?',
      answer:
          '아니요. 학과, 학년, RA 여부는 추천 생활권과 과 피하기 기능처럼 내부 추천 품질을 높이기 위해 사용되며, 다른 사용자 프로필에는 표시하지 않습니다.',
    ),
    _FaqItem(
      question: '과 피하기는 어떤 기능인가요?',
      answer:
          '설정에서 과 피하기를 켜면 같은 학과 사용자가 추천에서 제외되도록 돕습니다. 단, 추천 상황이나 데이터 상태에 따라 완전한 제외를 보장하지는 않을 수 있습니다.',
    ),
    _FaqItem(
      question: '채팅방에서 약속 기능은 어떻게 쓰나요?',
      answer:
          '채팅방 상단의 약속잡기 버튼을 눌러 시간과 장소를 정할 수 있습니다. 약속이 확정되면 채팅방 안에서 약속 정보와 안전도장 흐름을 확인할 수 있습니다.',
    ),
    _FaqItem(
      question: '계정을 탈퇴하면 어떻게 되나요?',
      answer:
          '탈퇴 즉시 프로필은 비공개 처리되고 추천과 채팅 전송이 중단됩니다. 기존 채팅방에는 상대방 보호를 위해 탈퇴한 사용자로 표시되며, 일반 탈퇴자는 이후 재가입할 수 있습니다.',
    ),
    _FaqItem(
      question: '신고나 문의는 어디로 보내나요?',
      answer:
          '앱 설정의 의견 보내기, 문제 신고, 고객 센터를 이용해주세요. 고객 센터 이메일은 seolleyeon.official@gmail.com 입니다.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final bgColor = isDark ? AppColorsDark.background : const Color(0xFFF8F6F6);

    return CupertinoPageScaffold(
      backgroundColor: bgColor,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: seol.cardSurface.withValues(alpha: 0.8),
        border: null,
        middle: Text(
          '자주 묻는 질문',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: textMain,
          ),
        ),
      ),
      child: SafeArea(
        child: ListView.separated(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 48),
          itemCount: _items.length,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (context, index) => _FaqTile(item: _items[index]),
        ),
      ),
    );
  }
}

class _FaqTile extends StatelessWidget {
  final _FaqItem item;

  const _FaqTile({required this.item});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textMain = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF181113);
    final textSub = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF89616B);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(
              alpha: isDark ? 0.12 : 0.03,
            ),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.question,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 16,
              fontWeight: FontWeight.w800,
              height: 1.35,
              color: textMain,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            item.answer,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              height: 1.5,
              color: textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class _FaqItem {
  final String question;
  final String answer;

  const _FaqItem({required this.question, required this.answer});
}
