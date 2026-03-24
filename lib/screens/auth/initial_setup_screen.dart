import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../services/user_service.dart';

class InitialSetupScreen extends StatefulWidget {
  const InitialSetupScreen({super.key});

  @override
  State<InitialSetupScreen> createState() => _InitialSetupScreenState();
}

class _InitialSetupScreenState extends State<InitialSetupScreen> {
  final _formKey = GlobalKey<FormState>();
  final _userService = UserService();
  final _userNameController = TextEditingController();
  final _nicknameController = TextEditingController();
  final _introductionController = TextEditingController();
  final _mbtiController = TextEditingController();
  final _attachmentTypeController = TextEditingController();
  final _interestsController = TextEditingController();
  final _lifestyleController = TextEditingController();
  final _preferredMbtiController = TextEditingController();
  final _preferredAttachmentTypeController = TextEditingController();
  final _preferredHeightController = TextEditingController();
  final _preferredAgeController = TextEditingController();
  final _preferredLifestyleController = TextEditingController();

  String? _gender;
  String? _department;
  String? _preferredGender;
  String? _preferredDepartment;
  String? _kakaoUserId;
  Map<String, dynamic>? _kakaoUserInfo;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadKakaoInfo());
  }

  Future<void> _loadKakaoInfo() async {
    final authProvider = context.read<AuthProvider>();
    _kakaoUserId = authProvider.kakaoUserId;
    _kakaoUserInfo = authProvider.kakaoUserInfo;
    if (_kakaoUserInfo != null) {
      setState(() {
        _nicknameController.text = _kakaoUserInfo?['nickname'] ?? '';
        _userNameController.text = _kakaoUserInfo?['nickname'] ?? '';
      });
    }
  }

  @override
  void dispose() {
    _userNameController.dispose();
    _nicknameController.dispose();
    _introductionController.dispose();
    _mbtiController.dispose();
    _attachmentTypeController.dispose();
    _interestsController.dispose();
    _lifestyleController.dispose();
    _preferredMbtiController.dispose();
    _preferredAttachmentTypeController.dispose();
    _preferredHeightController.dispose();
    _preferredAgeController.dispose();
    _preferredLifestyleController.dispose();
    super.dispose();
  }

  Future<void> _saveToFirestore() async {
    if (!_formKey.currentState!.validate()) return;
    if (_kakaoUserId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('카카오 로그인 정보가 없습니다.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    setState(() => _isLoading = true);

    final authProvider = context.read<AuthProvider>();
    final extraFields = {
      'name': _userNameController.text.trim(),
      'nickname': _nicknameController.text.trim(),
      'gender': _gender,
      'introduction': _introductionController.text.trim(),
      'mbti': _mbtiController.text.trim(),
      'attachmentType': _attachmentTypeController.text.trim(),
      'department': _department,
      'interests': _interestsController.text.trim(),
      'lifestyle': _lifestyleController.text.trim(),
      'preferredGender': _preferredGender,
      'preferredMbti': _preferredMbtiController.text.trim(),
      'preferredAttachmentType': _preferredAttachmentTypeController.text.trim(),
      'preferredDepartment': _preferredDepartment,
      'preferredHeight': _preferredHeightController.text.trim(),
      'preferredAge': _preferredAgeController.text.trim(),
      'preferredLifestyle': _preferredLifestyleController.text.trim(),
      'initialSetupComplete': true,
    };

    if (authProvider.isStudentVerified &&
        authProvider.studentEmail != null &&
        authProvider.studentEmail!.isNotEmpty) {
      extraFields['studentEmail'] = authProvider.studentEmail;
      extraFields['isStudentVerified'] = true;
    }

    try {
      await _userService.upsertKakaoUser(
        kakaoUserId: _kakaoUserId!,
        nickname: _kakaoUserInfo?['nickname'],
        profileImageUrl: _kakaoUserInfo?['profileImageUrl'],
        email: _kakaoUserInfo?['email'],
        extraFields: extraFields,
      );

      if (!mounted) return;
      authProvider.markInitialSetupComplete();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('프로필이 성공적으로 저장되었습니다!'),
          backgroundColor: Colors.green,
        ),
      );
      context.go('/home');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('저장 실패: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('초기 설정')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '프로필을 설정해주세요',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),
              _buildSection(
                title: '기본 정보',
                children: [
                  _buildTextField('사용자 이름', _userNameController),
                  _buildTextField('닉네임', _nicknameController),
                  _buildDropdown(
                    '성별',
                    ['남성', '여성'],
                    _gender,
                    (value) => setState(() => _gender = value),
                  ),
                  _buildTextField(
                    '자기소개 (선택)',
                    _introductionController,
                    isOptional: true,
                  ),
                  _buildImagePicker('사진 등록'),
                  _buildTextField('MBTI', _mbtiController),
                  _buildTextField('애착유형', _attachmentTypeController),
                  _buildDropdown(
                    '학과계열',
                    ['문과', '이과', '예체', '메디컬'],
                    _department,
                    (value) => setState(() => _department = value),
                  ),
                  _buildTextField(
                    '관심사 (선택)',
                    _interestsController,
                    isOptional: true,
                  ),
                  _buildTextField('생활 습관 (담배, 종교 등)', _lifestyleController),
                ],
              ),
              const SizedBox(height: 32),
              _buildSection(
                title: '선호 취향',
                children: [
                  _buildDropdown(
                    '선호 성별',
                    ['남성', '여성', '상관없음'],
                    _preferredGender,
                    (value) => setState(() => _preferredGender = value),
                  ),
                  _buildTextField('선호 MBTI', _preferredMbtiController),
                  _buildTextField(
                    '선호 애착유형',
                    _preferredAttachmentTypeController,
                  ),
                  _buildDropdown(
                    '선호 학과계열',
                    ['문과', '이과', '예체', '메디컬'],
                    _preferredDepartment,
                    (value) => setState(() => _preferredDepartment = value),
                  ),
                  _buildTextField('선호 키', _preferredHeightController),
                  _buildTextField('선호 나이', _preferredAgeController),
                  _buildTextField(
                    '기타 생활 습관 비선호 항목',
                    _preferredLifestyleController,
                  ),
                ],
              ),
              const SizedBox(height: 32),
              ElevatedButton(
                onPressed: _isLoading ? null : _saveToFirestore,
                style: ElevatedButton.styleFrom(
                  minimumSize: const Size(double.infinity, 50),
                ),
                child: _isLoading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(
                            Colors.white,
                          ),
                        ),
                      )
                    : const Text('완료'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSection({
    required String title,
    required List<Widget> children,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        ...children,
      ],
    );
  }

  Widget _buildTextField(
    String label,
    TextEditingController controller, {
    bool isOptional = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16.0),
      child: TextFormField(
        controller: controller,
        style: const TextStyle(fontFamily: 'Noto Sans KR'),
        decoration: InputDecoration(
          labelText: label + (isOptional ? '' : ''),
          border: const OutlineInputBorder(),
        ),
        validator: isOptional
            ? null
            : (value) {
                if (value == null || value.trim().isEmpty) {
                  return '${label.replaceAll(' (선택)', '')}을(를) 입력해주세요';
                }
                return null;
              },
      ),
    );
  }

  Widget _buildDropdown(
    String label,
    List<String> items,
    String? value,
    ValueChanged<String?> onChanged,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16.0),
      child: DropdownButtonFormField<String>(
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        // ignore: deprecated_member_use
        value: value,
        items: items
            .map((item) => DropdownMenuItem(value: item, child: Text(item)))
            .toList(),
        onChanged: onChanged,
        validator: (value) {
          if (value == null || value.isEmpty) {
            return '$label을(를) 선택해주세요';
          }
          return null;
        },
      ),
    );
  }

  Widget _buildImagePicker(String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () {
              // TODO: Implement image picker
            },
            icon: const Icon(Icons.add_photo_alternate),
            label: const Text('사진 추가'),
          ),
        ],
      ),
    );
  }
}
