import 'package:flutter/material.dart';

class AvatarGeneratingOverlay extends StatelessWidget {
  const AvatarGeneratingOverlay({super.key});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xCCFFF8FB),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Container(
            margin: const EdgeInsets.all(24),
            padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.94),
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFF0DCE5)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFFE48CB1).withValues(alpha: 0.16),
                  blurRadius: 30,
                  offset: const Offset(0, 14),
                ),
              ],
            ),
            child: const Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 36,
                  height: 36,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: Color(0xFFE48CB1),
                  ),
                ),
                SizedBox(height: 18),
                Text(
                  '아바타 생성중...',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFF4A313B),
                  ),
                ),
                SizedBox(height: 10),
                Text(
                  '프로필에는 실제 사진이 아닌 아바타가 표시돼요.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.45,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF9A7785),
                  ),
                ),
                SizedBox(height: 6),
                Text(
                  '잠시만 기다려주세요. 안전한 프로필 이미지를 만들고 있어요.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.45,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF9A7785),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
