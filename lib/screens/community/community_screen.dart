import 'package:flutter/material.dart';

class CommunityScreen extends StatelessWidget {
  const CommunityScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('대나무숲')),
      body: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.forest, size: 80, color: Colors.green),
            SizedBox(height: 16),
            Text(
              '대나무숲',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text('연애 관련 커뮤니티', style: TextStyle(color: Colors.grey)),
            SizedBox(height: 32),
            Text('커뮤니티 기능이 곧 추가될 예정입니다', style: TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}
