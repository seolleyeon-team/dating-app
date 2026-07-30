import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class TermsScreen extends StatefulWidget {
  const TermsScreen({super.key});

  @override
  State<TermsScreen> createState() => _TermsScreenState();
}

class _TermsScreenState extends State<TermsScreen> {
  bool _requiredTermsAgreed = false;
  bool _optionalTermsAgreed = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('약관 동의')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '서비스 이용을 위해 약관에 동의해주세요',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 24),

            // Required Terms
            _buildTermsItem(
              title: '필수 약관 1',
              isRequired: true,
              isAgreed: _requiredTermsAgreed,
              onChanged: (value) {
                setState(() {
                  _requiredTermsAgreed = value;
                });
              },
            ),
            const SizedBox(height: 16),
            _buildTermsItem(
              title: '필수 약관 2',
              isRequired: true,
              isAgreed: _requiredTermsAgreed,
              onChanged: (value) {
                setState(() {
                  _requiredTermsAgreed = value;
                });
              },
            ),
            const SizedBox(height: 24),

            // Optional Terms
            _buildTermsItem(
              title: '선택 약관',
              isRequired: false,
              isAgreed: _optionalTermsAgreed,
              onChanged: (value) {
                setState(() {
                  _optionalTermsAgreed = value;
                });
              },
            ),
            const SizedBox(height: 32),

            // Agreement Message
            if (!_requiredTermsAgreed)
              const Padding(
                padding: EdgeInsets.only(bottom: 16.0),
                child: Text(
                  '앱에 가입하려면 먼저 필수 약관에 동의를 해야합니다',
                  style: TextStyle(color: Colors.orange, fontSize: 12),
                ),
              ),

            // Next Button
            ElevatedButton(
              onPressed: _requiredTermsAgreed
                  ? () {
                      context.push('/auth/kakao');
                    }
                  : null,
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(double.infinity, 50),
              ),
              child: const Text('다음'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTermsItem({
    required String title,
    required bool isRequired,
    required bool isAgreed,
    required ValueChanged<bool> onChanged,
  }) {
    return Row(
      children: [
        Checkbox(
          value: isAgreed,
          onChanged: (value) => onChanged(value ?? false),
        ),
        Expanded(
          child: Row(
            children: [
              Text(title),
              if (isRequired)
                const Text(' (필수)', style: TextStyle(color: Colors.red)),
            ],
          ),
        ),
        TextButton(
          onPressed: () {
            // Show terms detail
          },
          child: const Text('보기'),
        ),
      ],
    );
  }
}
