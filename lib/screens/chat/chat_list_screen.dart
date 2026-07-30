import 'package:flutter/material.dart';

class ChatListScreen extends StatelessWidget {
  const ChatListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('채팅'),
      ),
      body: ListView(
        children: [
          // 1:1 Chat Section
          _buildSectionHeader('1대1 채팅'),
          _buildChatItem(
            title: '1대1 채팅',
            onTap: () {
              // TODO: Navigate to 1:1 chat
            },
          ),
          _buildChatItem(
            title: '3대3 채팅',
            onTap: () {
              // TODO: Navigate to 3:3 chat
            },
          ),
          _buildChatItem(
            title: '채팅 어시스턴트',
            onTap: () {
              // TODO: Navigate to chat assistant
            },
          ),
          
          const Divider(),
          
          // Chat Rooms
          _buildSectionHeader('채팅방'),
          // TODO: Load actual chat rooms
          const Padding(
            padding: EdgeInsets.all(16.0),
            child: Text(
              '채팅방이 없습니다',
              style: TextStyle(
                color: Colors.grey,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildChatItem({
    required String title,
    required VoidCallback onTap,
  }) {
    return ListTile(
      title: Text(title),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
