import 'package:flutter/material.dart';

class MatchingScreen extends StatelessWidget {
  const MatchingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('설레연'),
        actions: [
          IconButton(
            icon: const Icon(Icons.filter_list),
            onPressed: () {
              // TODO: Show filter options
            },
          ),
        ],
      ),
      body: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              '인연 추천 페이지',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 16),
            Text(
              'AI 기반 매칭 기능이 여기에 표시됩니다',
              style: TextStyle(color: Colors.grey),
            ),
            SizedBox(height: 32),
            Text('주요 기능:', style: TextStyle(fontWeight: FontWeight.bold)),
            SizedBox(height: 8),
            Text('• AI 사진으로 사용자 취향 필터링'),
            Text('• AI로 실제 인연 추천'),
            Text('• 매칭 요청 및 프로필 보기'),
          ],
        ),
      ),
    );
  }
}
