// =============================================================================
// 기본 정보 입력 화면 (온보딩 Step 1 Update)
// 경로: lib/features/onboarding/screens/basic_info_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const BasicInfoScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF6B7280);
  static const Color border = Color(0xFFE5E7EB);
  static const Color inputBg = Color(0xFFF9FAFB); // gray-50
  static const Color progressBg = Color(0xFFE6DBDF);
}

// =============================================================================
// 데이터 모델
// =============================================================================
enum Gender { male, female, other }

enum MbtiE { e, i }

enum MbtiN { n, s }

enum MbtiF { f, t }

enum MbtiJ { j, p }

enum RelationshipPreference { serious, friend, open }

// =============================================================================
// 메인 화면
// =============================================================================
class BasicInfoScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final Function(
    String nickname,
    Gender gender,
    String region,
    String education,
    int height,
    int age,
    String mbti,
    List<String> loveLanguages,
    RelationshipPreference relationship,
  )?
  onNext;

  const BasicInfoScreen({
    super.key,
    this.currentStep = 1,
    this.totalSteps = 8,
    this.onBack,
    this.onNext,
  });

  @override
  State<BasicInfoScreen> createState() => _BasicInfoScreenState();
}

class _BasicInfoScreenState extends State<BasicInfoScreen> {
  final TextEditingController _nicknameController = TextEditingController();
  final TextEditingController _heightController = TextEditingController();
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  Gender? _gender = Gender.female;
  String? _selectedRegion;
  String? _selectedEducation;
  double _age = 23;

  // MBTI
  MbtiE _mbtiE = MbtiE.e;
  MbtiN _mbtiN = MbtiN.n;
  MbtiF _mbtiF = MbtiF.f;
  MbtiJ _mbtiJ = MbtiJ.j;

  final List<String> _loveLanguages = ['인정하는 말 💬', '스킨십 ❤️']; // 초기값 예시
  RelationshipPreference _relationship = RelationshipPreference.serious;
  bool _isSavingOnExit = false;

  @override
  void initState() {
    super.initState();
    _loadExistingBasicInfo();
  }

  Future<void> _loadExistingBasicInfo() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;
    final nickname = onboarding['nickname']?.toString() ?? '';
    final genderStr = onboarding['gender']?.toString() ?? '';
    final region = onboarding['region']?.toString();
    final education = onboarding['education']?.toString();
    final height = onboarding['height'];
    final age = onboarding['age'];
    final mbtiStr = (onboarding['mbti']?.toString() ?? '').toLowerCase();
    final loveLanguagesRaw = onboarding['loveLanguages'];
    final relationshipStr = onboarding['relationship']?.toString() ?? '';
    if (nickname.isNotEmpty) _nicknameController.text = nickname;
    if (height is int && height > 0) _heightController.text = height.toString();
    if (age is int && age > 0) _age = age.toDouble();
    if (region != null && region.isNotEmpty) _selectedRegion = region;
    if (education != null && education.isNotEmpty) _selectedEducation = education;
    if (genderStr == 'male') _gender = Gender.male;
    else if (genderStr == 'female') _gender = Gender.female;
    else if (genderStr == 'other') _gender = Gender.other;
    if (mbtiStr.length >= 4) {
      if (mbtiStr[0] == 'e') _mbtiE = MbtiE.e; else if (mbtiStr[0] == 'i') _mbtiE = MbtiE.i;
      if (mbtiStr.length > 1) { if (mbtiStr[1] == 'n') _mbtiN = MbtiN.n; else if (mbtiStr[1] == 's') _mbtiN = MbtiN.s; }
      if (mbtiStr.length > 2) { if (mbtiStr[2] == 'f') _mbtiF = MbtiF.f; else if (mbtiStr[2] == 't') _mbtiF = MbtiF.t; }
      if (mbtiStr.length > 3) { if (mbtiStr[3] == 'j') _mbtiJ = MbtiJ.j; else if (mbtiStr[3] == 'p') _mbtiJ = MbtiJ.p; }
    }
    if (loveLanguagesRaw is List && loveLanguagesRaw.isNotEmpty) {
      _loveLanguages
        ..clear()
        ..addAll(loveLanguagesRaw.map((e) => e.toString()));
    }
    if (relationshipStr == 'serious') _relationship = RelationshipPreference.serious;
    else if (relationshipStr == 'friend') _relationship = RelationshipPreference.friend;
    else if (relationshipStr == 'open') _relationship = RelationshipPreference.open;
    if (mounted) setState(() {});
  }

  Future<void> _saveCurrentBasicInfo() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      final mbti = '${_mbtiE.name.toUpperCase()}${_mbtiN.name.toUpperCase()}${_mbtiF.name.toUpperCase()}${_mbtiJ.name.toUpperCase()}';
      await OnboardingSaveHelper.saveBasicInfo(
        nickname: _nicknameController.text,
        gender: _gender?.name ?? '',
        region: _selectedRegion ?? '',
        education: _selectedEducation ?? '',
        height: int.tryParse(_heightController.text) ?? 0,
        age: _age.round(),
        mbti: mbti,
        loveLanguages: _loveLanguages,
        relationship: _relationship.name,
      );
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentBasicInfo();
    if (!mounted) return;
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    _heightController.dispose();
    super.dispose();
  }

  void _toggleLoveLanguage(String language) {
    HapticFeedback.lightImpact();
    setState(() {
      if (_loveLanguages.contains(language)) {
        _loveLanguages.remove(language);
      } else {
        _loveLanguages.add(language);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handleBack();
      },
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: _AppColors.backgroundLight,
          body: SafeArea(
            child: Stack(
              children: [
                Column(
                  children: [
                    // 헤더
                    _Header(
                      currentStep: widget.currentStep,
                      totalSteps: widget.totalSteps,
                    ),
                    // 메인 콘텐츠
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 안내 섹션
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(24),
                            margin: const EdgeInsets.only(bottom: 24),
                            decoration: BoxDecoration(
                              color: _AppColors.surfaceLight,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.5),
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.05),
                                  blurRadius: 24,
                                  offset: const Offset(0, 4),
                                ),
                              ],
                            ),
                            child: Column(
                              children: const [
                                Text(
                                  '기본 정보',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 24,
                                    fontWeight: FontWeight.bold,
                                    color: _AppColors.textMain,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  '매칭을 위해 기본 정보를 입력해주세요.',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 14,
                                    color: _AppColors.textSub,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // 닉네임
                          _InputField(
                            label: '닉네임',
                            icon: Icons.person_outline_rounded,
                            footer: '나중에 프로필에서 수정할 수 있어요',
                            child: TextField(
                              controller: _nicknameController,
                              decoration: _inputDecoration('닉네임을 입력해주세요')
                                  .copyWith(
                                    prefixIcon: Icon(
                                      Icons.person_outline_rounded,
                                      color: Color(0xFF9CA3AF),
                                      size: 20,
                                    ),
                                    prefixIconConstraints: const BoxConstraints(
                                      minWidth: 44,
                                    ),
                                  ),
                              style: const TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 16,
                              ),
                            ),
                          ),

                          // 성별
                          _LabelSection(
                            label: '성별',
                            child: Container(
                              padding: const EdgeInsets.all(4),
                              decoration: BoxDecoration(
                                color: _AppColors.inputBg,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Row(
                                children: [
                                  _GenderOption(
                                    label: '남성',
                                    value: Gender.male,
                                    groupValue: _gender,
                                    onChanged: (v) =>
                                        setState(() => _gender = v),
                                  ),
                                  _GenderOption(
                                    label: '여성',
                                    value: Gender.female,
                                    groupValue: _gender,
                                    onChanged: (v) =>
                                        setState(() => _gender = v),
                                  ),
                                  _GenderOption(
                                    label: '기타',
                                    value: Gender.other,
                                    groupValue: _gender,
                                    onChanged: (v) =>
                                        setState(() => _gender = v),
                                  ),
                                ],
                              ),
                            ),
                          ),

                          // 거주 지역
                          // _InputField(
                          //   label: '거주 지역',
                          //   icon: Icons.location_on_outlined,
                          //   child: DropdownButtonFormField<String>(
                          //     // value: _selectedRegion, // value 대신 상태 관리되는 변수를 직접 사용하거나, 초기값 설정 필요 시 다른 방식 사용. DropdownButtonFormField에서 value는 현재 선택된 값을 의미함.
                          //     // 3.33.0 이후 deprecation 메시지: 'value' is deprecated and shouldn't be used. Use initialValue instead.
                          //     // 그러나 DropdownButtonFormField는 보통 value를 사용하여 상태를 동기화함. 여기서는 analyze 경고에 따라 initialValue를 고려할 수 있으나,
                          //     // 일반적인 패턴인 value 사용을 유지하되, 만약 flutter SDK 버전 문제라면 ignore 처리하거나,
                          //     // 여기서는 경고 메시지에 따라 value -> initialValue 로 변경 시도.
                          //     // 하지만 DropdownButtonFormField는 value가 변경되면 UI가 업데이트되어야 하므로 value 속성이 필수적임.
                          //     // 'initialValue'은 FormField 초기값임.
                          //     // 에러 메시지: Use initialValue instead. This will set the initial value for the form field. This feature was deprecated after v3.33.0-1.0.pre
                          //     // -> 이는 value를 초기값 용도로만 쓸 때의 경고일 수 있음. 여기서는 상태 변경(_selectedRegion)을 반영해야 하므로 value가 맞음.
                          //     // 다만, FormField로서의 사용법을 준수하기 위해 value 사용.
                          //     // 경고 무시 또는 SDK 버전 호환성 문제일 수 있음. 여기서는 value를 그대로 두고 @override 없이 사용.
                          //     // 또는 DropdownButtonFormField 대신 DropdownButton을 사용해야 할 수도 있음.
                          //     // 여기서는 일단 value를 유지하고, 경고가 발생했으므로 ignore 주석을 추가하거나,
                          //     // 더 안전한 방법은 아래와 같이 value를 유지하되 분석기의 지적 사항을 확인.
                          //     // 경고: 'value' is deprecated... Use initialValue instead.
                          //     // -> DropdownButtonFormField에서는 value가 현재 선택된 값을 제어함.
                          //     // 만약 단순히 초기값만 설정하는 것이라면 initialValue를 쓰라는 뜻.
                          //     // 여기서는 setState로 값을 바꾸므로 value가 필요함.
                          //     // 경고를 없애기 위해 value를 놔두고, 만약 최신 플러터 변경사항이라면 value가 감싸진 형태일 수 있음.
                          //     // 일단 value를 그대로 둡니다.
                          //     // ignore: deprecated_member_use
                          //     value: _selectedRegion,
                          //     decoration: _inputDecoration('지역을 선택해주세요'),
                          //     icon: const Icon(Icons.expand_more_rounded),
                          //     items: const [
                          //       DropdownMenuItem(
                          //         value: 'seoul',
                          //         child: Text('서울'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'gyeonggi',
                          //         child: Text('경기'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'incheon',
                          //         child: Text('인천'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'busan',
                          //         child: Text('부산'),
                          //       ),
                          //     ],
                          //     onChanged: (v) =>
                          //         setState(() => _selectedRegion = v),
                          //   ),
                          // ),

                          // // 학력
                          // _InputField(
                          //   label: '학력',
                          //   icon: Icons.school_outlined,
                          //   child: DropdownButtonFormField<String>(
                          //     // ignore: deprecated_member_use
                          //     value: _selectedEducation,
                          //     decoration: _inputDecoration('학력을 선택해주세요'),
                          //     icon: const Icon(Icons.expand_more_rounded),
                          //     items: const [
                          //       DropdownMenuItem(
                          //         value: 'hs',
                          //         child: Text('고등학교 졸업'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'univ_att',
                          //         child: Text('대학교 재학'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'univ_grad',
                          //         child: Text('대학교 졸업'),
                          //       ),
                          //       DropdownMenuItem(
                          //         value: 'grad_sch',
                          //         child: Text('대학원 재학/졸업'),
                          //       ),
                          //     ],
                          //     onChanged: (v) =>
                          //         setState(() => _selectedEducation = v),
                          //   ),
                          // ),

                          // 키
                          _InputField(
                            label: '키',
                            icon: Icons.height_rounded,
                            child: Stack(
                              alignment: Alignment.centerRight,
                              children: [
                                TextField(
                                  controller: _heightController,
                                  keyboardType: TextInputType.number,
                                  decoration: _inputDecoration('170').copyWith(
                                    prefixIcon: IconButton(
                                      icon: const Icon(
                                        Icons.height_rounded,
                                        color: Color(0xFF9CA3AF),
                                        size: 20,
                                      ),
                                      onPressed: () async {
                                        HapticFeedback.selectionClick();
                                        final currentHeight =
                                            int.tryParse(_heightController.text) ??
                                                175;
                                        final result = await Navigator.of(
                                          context,
                                          rootNavigator: true,
                                        ).pushNamed<int>(
                                          RouteNames.onboardingHeightSelection,
                                          arguments: {
                                            'initialHeight': currentHeight
                                                .clamp(140, 200),
                                          },
                                        );
                                        if (result != null && mounted) {
                                          setState(() =>
                                              _heightController.text =
                                                  result.toString());
                                        }
                                      },
                                    ),
                                    prefixIconConstraints: const BoxConstraints(
                                      minWidth: 44,
                                    ),
                                    contentPadding: const EdgeInsets.only(
                                      left: 44,
                                      right: 48,
                                      top: 14,
                                      bottom: 14,
                                    ),
                                  ),
                                  style: const TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 16,
                                  ),
                                ),
                                const Positioned(
                                  right: 16,
                                  child: Text(
                                    'cm',
                                    style: TextStyle(
                                      color: _AppColors.textSub,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // 나이
                          _LabelSection(
                            label: '나이',
                            child: Column(
                              children: [
                                SliderTheme(
                                  data: SliderThemeData(
                                    trackHeight: 4,
                                    activeTrackColor: _AppColors.primary,
                                    inactiveTrackColor: _AppColors.border,
                                    thumbColor: const Color(0xFFFFC2D4),
                                    thumbShape: const RoundSliderThumbShape(
                                      enabledThumbRadius: 12,
                                    ),
                                    overlayColor: _AppColors.primary.withValues(
                                      alpha: 0.1,
                                    ),
                                  ),
                                  child: Slider(
                                    value: _age,
                                    min: 18,
                                    max: 30,
                                    onChanged: (v) => setState(() => _age = v),
                                  ),
                                ),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment:
                                      CrossAxisAlignment.baseline,
                                  textBaseline: TextBaseline.alphabetic,
                                  children: [
                                    Text(
                                      '${_age.round()}',
                                      style: const TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontSize: 24,
                                        fontWeight: FontWeight.bold,
                                        color: _AppColors.textMain,
                                      ),
                                    ),
                                    const SizedBox(width: 4),
                                    const Text(
                                      '살',
                                      style: TextStyle(
                                        fontSize: 18,
                                        fontWeight: FontWeight.w500,
                                        color: _AppColors.textMain,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),

                          // MBTI
                          _LabelSection(
                            label: 'MBTI',
                            child: Container(
                              padding: const EdgeInsets.all(8),
                              child: Row(
                                children: [
                                  // E/I
                                  Expanded(
                                    child: Column(
                                      children: [
                                        _MbtiButton(
                                          text: 'E',
                                          isSelected: _mbtiE == MbtiE.e,
                                          onTap: () =>
                                              setState(() => _mbtiE = MbtiE.e),
                                        ),
                                        const SizedBox(height: 16),
                                        _MbtiButton(
                                          text: 'I',
                                          isSelected: _mbtiE == MbtiE.i,
                                          onTap: () =>
                                              setState(() => _mbtiE = MbtiE.i),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  // N/S
                                  Expanded(
                                    child: Column(
                                      children: [
                                        _MbtiButton(
                                          text: 'N',
                                          isSelected: _mbtiN == MbtiN.n,
                                          onTap: () =>
                                              setState(() => _mbtiN = MbtiN.n),
                                        ),
                                        const SizedBox(height: 16),
                                        _MbtiButton(
                                          text: 'S',
                                          isSelected: _mbtiN == MbtiN.s,
                                          onTap: () =>
                                              setState(() => _mbtiN = MbtiN.s),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  // F/T
                                  Expanded(
                                    child: Column(
                                      children: [
                                        _MbtiButton(
                                          text: 'F',
                                          isSelected: _mbtiF == MbtiF.f,
                                          onTap: () =>
                                              setState(() => _mbtiF = MbtiF.f),
                                        ),
                                        const SizedBox(height: 16),
                                        _MbtiButton(
                                          text: 'T',
                                          isSelected: _mbtiF == MbtiF.t,
                                          onTap: () =>
                                              setState(() => _mbtiF = MbtiF.t),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  // J/P
                                  Expanded(
                                    child: Column(
                                      children: [
                                        _MbtiButton(
                                          text: 'J',
                                          isSelected: _mbtiJ == MbtiJ.j,
                                          onTap: () =>
                                              setState(() => _mbtiJ = MbtiJ.j),
                                        ),
                                        const SizedBox(height: 16),
                                        _MbtiButton(
                                          text: 'P',
                                          isSelected: _mbtiJ == MbtiJ.p,
                                          onTap: () =>
                                              setState(() => _mbtiJ = MbtiJ.p),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),

                          const Divider(
                            height: 48,
                            thickness: 1,
                            color: _AppColors.border,
                          ),

                          // 사랑의 언어
                          _LabelSection(
                            label: '사랑의 언어',
                            subLabel: '(중복 선택 가능)',
                            child: Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children:
                                  [
                                    '인정하는 말 💬',
                                    '함께하는 시간 🕰️',
                                    '선물 🎁',
                                    '봉사 🧹',
                                    '스킨십 ❤️',
                                  ].map((lang) {
                                    final isSelected = _loveLanguages.contains(
                                      lang,
                                    );
                                    return GestureDetector(
                                      onTap: () => _toggleLoveLanguage(lang),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 12,
                                          vertical: 8,
                                        ),
                                        decoration: BoxDecoration(
                                          color: isSelected
                                              ? _AppColors.primary.withValues(
                                                  alpha: 0.1,
                                                )
                                              : _AppColors.inputBg,
                                          borderRadius: BorderRadius.circular(
                                            20,
                                          ),
                                          border: Border.all(
                                            color: isSelected
                                                ? _AppColors.primary.withValues(
                                                    alpha: 0.2,
                                                  )
                                                : _AppColors.border,
                                          ),
                                        ),
                                        child: Text(
                                          lang,
                                          style: TextStyle(
                                            color: isSelected
                                                ? _AppColors.primary
                                                : _AppColors.textSub,
                                            fontSize: 14,
                                            fontWeight: FontWeight.w500,
                                          ),
                                        ),
                                      ),
                                    );
                                  }).toList(),
                            ),
                          ),

                          const SizedBox(height: 24),

                          // 선호하는 관계
                          _LabelSection(
                            label: '선호하는 관계',
                            child: Column(
                              children: [
                                _RelationshipOption(
                                  label: '진지한 연애를 원해요',
                                  value: RelationshipPreference.serious,
                                  groupValue: _relationship,
                                  onChanged: (v) =>
                                      setState(() => _relationship = v),
                                ),
                                const SizedBox(height: 8),
                                _RelationshipOption(
                                  label: '편안한 친구 같은 관계',
                                  value: RelationshipPreference.friend,
                                  groupValue: _relationship,
                                  onChanged: (v) =>
                                      setState(() => _relationship = v),
                                ),
                                const SizedBox(height: 8),
                                _RelationshipOption(
                                  label: '일단 만나보고 결정할래요',
                                  value: RelationshipPreference.open,
                                  groupValue: _relationship,
                                  onChanged: (v) =>
                                      setState(() => _relationship = v),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              // 하단 버튼
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _BottomButton(
                  onNext: () async {
                    HapticFeedback.mediumImpact();
                    try {
                      await _saveCurrentBasicInfo();
                    } catch (e) {
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('저장 실패: $e'),
                          backgroundColor: Colors.red,
                        ),
                      );
                      return;
                    }
                    if (!context.mounted) return;
                    final mbti = '${_mbtiE.name.toUpperCase()}${_mbtiN.name.toUpperCase()}${_mbtiF.name.toUpperCase()}${_mbtiJ.name.toUpperCase()}';
                    if (widget.onNext != null) {
                      widget.onNext!.call(
                        _nicknameController.text,
                        _gender!,
                        _selectedRegion ?? '',
                        _selectedEducation ?? '',
                        int.tryParse(_heightController.text) ?? 0,
                        _age.round(),
                        mbti,
                        _loveLanguages,
                        _relationship,
                      );
                    } else {
                      Navigator.of(context)
                          .pushNamed(RouteNames.onboardingInterestsSelection);
                    }
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    ),
    );
  }

  InputDecoration _inputDecoration(String hint) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(
        fontFamily: 'Pretendard',
        color: Color(0xFF9CA3AF),
      ),
      filled: true,
      fillColor: _AppColors.inputBg,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _AppColors.primary, width: 2),
      ),
      prefixIconConstraints: const BoxConstraints(minWidth: 48),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight.withValues(alpha: 0.8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // 커스텀 프로그레스 인디케이터
          Row(
            children: List.generate(totalSteps, (index) {
              final isCurrent = index == currentStep - 1;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: isCurrent ? 24 : 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: isCurrent ? _AppColors.primary : _AppColors.progressBg,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 입력 필드 컨테이너
// =============================================================================
class _InputField extends StatelessWidget {
  final String label;
  final IconData icon;
  final Widget child;
  final String? footer;

  const _InputField({
    required this.label,
    required this.icon,
    required this.child,
    this.footer,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 8),
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.textMain,
              ),
            ),
          ),
          child,
          if (footer != null)
            Padding(
              padding: const EdgeInsets.only(left: 4, top: 4),
              child: Text(
                footer!,
                style: const TextStyle(fontSize: 12, color: Color(0xFF9CA3AF)),
              ),
            ),
        ],
      ),
    );
  }
}

// =============================================================================
// 라벨 섹션
// =============================================================================
class _LabelSection extends StatelessWidget {
  final String label;
  final String? subLabel;
  final Widget child;

  const _LabelSection({
    required this.label,
    this.subLabel,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 8),
            child: Row(
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textMain,
                  ),
                ),
                if (subLabel != null) ...[
                  const SizedBox(width: 4),
                  Text(
                    subLabel!,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.normal,
                      color: Color(0xFF9CA3AF),
                    ),
                  ),
                ],
              ],
            ),
          ),
          child,
        ],
      ),
    );
  }
}

// =============================================================================
// 성별 옵션 버튼
// =============================================================================
class _GenderOption extends StatelessWidget {
  final String label;
  final Gender value;
  final Gender? groupValue;
  final Function(Gender) onChanged;

  const _GenderOption({
    required this.label,
    required this.value,
    required this.groupValue,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isSelected = value == groupValue;
    return Expanded(
      child: GestureDetector(
        onTap: () {
          HapticFeedback.lightImpact();
          onChanged(value);
        },
        child: Container(
          height: 40,
          margin: const EdgeInsets.symmetric(horizontal: 2),
          decoration: BoxDecoration(
            color: isSelected ? Colors.white : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.05),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: isSelected
                  ? _AppColors.primary
                  : _AppColors.textSub.withValues(alpha: 0.5),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// MBTI 버튼
// =============================================================================
class _MbtiButton extends StatelessWidget {
  final String text;
  final bool isSelected;
  final VoidCallback onTap;

  const _MbtiButton({
    required this.text,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: double.infinity,
        height: 70, // AspectRatio 대신 고정 높이 또는 LayoutBuilder 사용

        decoration: BoxDecoration(
          color: isSelected ? Colors.white : _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected
                ? _AppColors.primary.withValues(alpha: 0.1)
                : Colors.white.withValues(alpha: 0.4),
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.15),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
        ),
        child: Center(
          child: Text(
            text,
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: isSelected
                  ? _AppColors.primary
                  : _AppColors.textSub.withValues(alpha: 0.5),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 관계 선호 옵션
// =============================================================================
class _RelationshipOption extends StatelessWidget {
  final String label;
  final RelationshipPreference value;
  final RelationshipPreference? groupValue;
  final Function(RelationshipPreference) onChanged;

  const _RelationshipOption({
    required this.label,
    required this.value,
    required this.groupValue,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isSelected = value == groupValue;
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onChanged(value);
      },
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isSelected
              ? _AppColors.primary.withValues(alpha: 0.05)
              : _AppColors.inputBg,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected
                ? _AppColors.primary.withValues(alpha: 0.3)
                : _AppColors.border,
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: isSelected ? _AppColors.primary : _AppColors.textSub,
                ),
              ),
            ),
            if (isSelected)
              const Icon(
                Icons.check_circle_rounded,
                color: _AppColors.primary,
                size: 20,
              ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 버튼
// =============================================================================
class _BottomButton extends StatelessWidget {
  final VoidCallback? onNext;

  const _BottomButton({this.onNext});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        16,
        16,
        16,
        MediaQuery.of(context).padding.bottom + 16,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight.withValues(alpha: 0.95),
            _AppColors.backgroundLight,
          ],
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onNext,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 12,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Text(
                '다음',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              SizedBox(width: 8),
              Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
