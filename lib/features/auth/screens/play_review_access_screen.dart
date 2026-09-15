import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../../../providers/auth_provider.dart';
import '../../../router/route_names.dart';
import '../../../services/play_review_access_service.dart';

class PlayReviewAccessScreen extends StatefulWidget {
  const PlayReviewAccessScreen({super.key});

  @override
  State<PlayReviewAccessScreen> createState() => _PlayReviewAccessScreenState();
}

class _PlayReviewAccessScreenState extends State<PlayReviewAccessScreen> {
  final _idController = TextEditingController();
  final _passwordController = TextEditingController();
  final _service = PlayReviewAccessService();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _idController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  String _messageFor(Object error) {
    if (error is FirebaseFunctionsException) {
      if (error.code == 'resource-exhausted') {
        return '로그인 시도가 잠시 제한되었습니다. 잠시 후 다시 시도해 주세요.';
      }
      if (error.code == 'unauthenticated') {
        return '심사 계정 ID 또는 비밀번호가 올바르지 않습니다.';
      }
      if (error.code == 'failed-precondition') {
        return '리뷰용 테스트 데이터가 준비되지 않았습니다. 개발자에게 문의해 주세요.';
      }
    }
    if (error.toString().contains('app_check_unavailable')) {
      return '앱 무결성 확인에 실패했습니다. 공식 앱 스토어에서 설치한 앱인지 확인해 주세요.';
    }
    return '심사용 로그인에 실패했습니다. 네트워크를 확인한 뒤 다시 시도해 주세요.';
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final id = _idController.text.trim();
    final password = _passwordController.text;
    if (id.isEmpty || password.isEmpty) {
      setState(() => _error = '아이디와 비밀번호를 모두 입력해 주세요.');
      return;
    }

    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await _service.signIn(loginId: id, password: password);
      if (!mounted) return;
      await context.read<AuthProvider>().refreshAfterExternalSignIn();
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
    } catch (error) {
      if (mounted) setState(() => _error = _messageFor(error));
    } finally {
      _passwordController.clear();
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(middle: Text('심사용 계정 로그인')),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 40, 24, 24),
          children: [
            const Text(
              '앱 심사용 계정',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            const Text(
              '앱 심사 안내에 제공된 심사 계정 ID와 비밀번호를 입력해 주세요.',
              style: TextStyle(fontSize: 15, height: 1.45),
            ),
            const SizedBox(height: 28),
            CupertinoTextField(
              controller: _idController,
              placeholder: 'Review ID',
              autocorrect: false,
              enableSuggestions: false,
              textInputAction: TextInputAction.next,
              padding: const EdgeInsets.all(16),
            ),
            const SizedBox(height: 12),
            CupertinoTextField(
              controller: _passwordController,
              placeholder: 'Password',
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              onSubmitted: (_) => _submit(),
              padding: const EdgeInsets.all(16),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: const TextStyle(color: CupertinoColors.systemRed),
              ),
            ],
            const SizedBox(height: 20),
            CupertinoButton.filled(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const CupertinoActivityIndicator(
                      color: CupertinoColors.white,
                    )
                  : const Text('로그인'),
            ),
          ],
        ),
      ),
    );
  }
}
