import 'package:flutter/material.dart';

import '../../router/route_names.dart';

/// 생활권 미설정 안내 + 보충 CTA.
///
/// 추천·미팅은 생활권이 같은 사용자끼리만 연결하므로, 생활권이 없는 계정은
/// 후보가 0명이 된다. 이때 "추천이 없습니다"만 보여주면 사용자가 해결할 수
/// 없으므로 어디서든 같은 안내와 해결 경로를 준다.
///
/// 1:1 추천 / 3:3 블라인드 취향 미팅 / 3:3 시즌 미팅이 모두 이 위젯을 쓴다.
class CampusLifeZonePrerequisite extends StatelessWidget {
  const CampusLifeZonePrerequisite({
    super.key,
    this.onCompleted,
    this.description,
  });

  /// 보충이 실제로 완료된 뒤 호출된다 (호출부가 데이터를 다시 읽도록).
  final Future<void> Function()? onCompleted;

  /// 진입점별 안내 문구. 없으면 공통 문구를 쓴다.
  final String? description;

  static Future<bool> open(BuildContext context) async {
    final result = await Navigator.of(
      context,
    ).pushNamed(RouteNames.campusLifeZoneRepair);
    return result == true;
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.place_outlined,
              size: 44,
              color: Color(0xFF9CA3AF),
            ),
            const SizedBox(height: 16),
            const Text(
              '생활권 설정이 필요해요',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: Color(0xFF1F2937),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              description ??
                  '신촌·송도 중 실제로 만날 수 있는 상대만 보여드리려고 해요.\n'
                      '학년과 학과만 알려주시면 바로 이용할 수 있어요.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 14,
                height: 1.6,
                color: Color(0xFF6B7280),
              ),
            ),
            const SizedBox(height: 20),
            SizedBox(
              height: 48,
              child: ElevatedButton(
                onPressed: () async {
                  final completed = await open(context);
                  if (completed && onCompleted != null) {
                    await onCompleted!();
                  }
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF3E3548),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 28),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                child: const Text(
                  '생활권 설정하기',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
