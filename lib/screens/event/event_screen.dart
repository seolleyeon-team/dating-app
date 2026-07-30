import 'package:flutter/material.dart';

class EventScreen extends StatelessWidget {
  const EventScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('이벤트'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          // 3:3 Meeting Section
          _buildEventCard(
            title: '3대3 미팅',
            description: 'Slot machine과 랜덤 매칭을 통해 3:3 미팅에 참여하세요',
            onTap: () {
              // TODO: Navigate to 3:3 meeting
            },
          ),
          
          const SizedBox(height: 16),
          
          // Partnership Section
          _buildEventCard(
            title: '제휴 (미팅 장소 추천)',
            description: '제휴 가게에서 미팅을 진행하고 특별한 혜택을 받아보세요',
            onTap: () {
              // TODO: Navigate to partnership
            },
          ),
          
          const SizedBox(height: 16),
          
          // 1:1 Gathering Section
          _buildEventCard(
            title: '1:1 소모임',
            description: '두쫀쿠 같이 만들기, 카페에서 카공하기, 영화 같이 보기 등',
            onTap: () {
              // TODO: Navigate to 1:1 gathering
            },
          ),
        ],
      ),
    );
  }

  Widget _buildEventCard({
    required String title,
    required String description,
    required VoidCallback onTap,
  }) {
    return Card(
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                description,
                style: const TextStyle(
                  color: Colors.grey,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
