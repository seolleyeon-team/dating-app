import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../../../constants/academic_grade_options.dart';
import '../../../constants/interest_taxonomy.dart';
import '../../../constants/profile_options.dart';
import '../../../constants/yonsei_departments.dart';
import '../../../services/avatar_source_photo_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/utils/avatar_lock_policy.dart';
import '../../../shared/widgets/profile_photo_mosaic.dart';
import '../../../router/route_names.dart';
import '../../matching/models/profile_card_args.dart';

class _AppColors {
  static const Color primary = Color(0xFFFF4B6E);
  static const Color backgroundLight = Color(0xFFF2F4F6);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF191F28);
  static const Color textSub = Color(0xFF8B95A1);
  static const Color placeholderBg = Color(0xFFF9FAFB);
}

// 온보딩·블라인드 미팅과 같은 taxonomy를 사용한다. 프로필 편집만 별도 목록을
// 유지하면 새 태그가 화면에서 누락되거나 저장된 라벨의 카테고리가 달라진다.
const List<InterestCategory> _interestCategories = interestCategories;

class ProfileEditScreen extends StatefulWidget {
  const ProfileEditScreen({super.key});

  @override
  State<ProfileEditScreen> createState() => _ProfileEditScreenState();
}

class _ProfileEditScreenState extends State<ProfileEditScreen> {
  final _userService = UserService();
  final _storageService = StorageService();

  bool _isLoading = true;
  bool _isSaving = false;

  String? _currentUserId;

  final List<String?> _photoSlots = List<String?>.filled(6, null);
  bool _avatarLocked = false;
  bool _avatarSourceLocked = false;
  String _lockedApprovedAvatarUrl = '';

  String _selfIntroduction = '';
  List<Map<String, String>> _profileQa = [];
  List<String> _interests = [];
  List<String> _keywords = [];
  List<String> _idealPersonalityKeywords = [];

  int? _height;
  int? _age; // Identity-linked onboarding value; intentionally read-only here.
  String _gender = '';
  String _grade = '';
  bool _isRa = false;
  String _relationship = '';
  String _mbti = '';
  String _major = '';
  String _department = '';
  String _nickname = '';
  String _drinking = '';
  String _smoking = '';
  String _exercise = '';
  String _religion = '';

  int? _idealMinAge;
  int? _idealMaxAge;
  int? _idealMinHeight;
  int? _idealMaxHeight;
  List<String> _idealMbti = [];
  List<String> _idealDepartments = [];
  String _idealDrinking = '';
  String _idealSmoking = '';
  String _idealExercise = '';
  String _idealReligion = '';
  bool _hasIdealTypeData = false;
  bool _idealTypeDirty = false;

  int? _parseInt(dynamic value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString().trim() ?? '');
  }

  List<String> _asStringList(dynamic value) {
    return value is List ? value.map((e) => e.toString()).toList() : [];
  }

  String? _nullableValue(String value) {
    final trimmed = value.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  Future<void> _openPreview() async {
    final kakaoUserId =
        _currentUserId ?? await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final previewOnboarding = <String, dynamic>{
      'nickname': _nickname.trim(),
      'selfIntroduction': _selfIntroduction.trim(),
      'age': _age,
      'gender': _gender,
      'height': _height,
      'grade': _grade,
      'isRa': _isRa,
      'mbti': _mbti,
      'major': _major,
      'department': _department,
      'relationship': _relationship,
      'interests': List<String>.from(_interests),
      'keywords': List<String>.from(_keywords),
      'loveLanguages': const <String>[],
      'avatarUrls': _photoSlots
          .whereType<String>()
          .where((url) => !AvatarSourcePhotoService.isQueuedSlotToken(url))
          .toList(),
      'profileQa': _profileQa
          .map(
            (e) => {
              'question': e['question']?.toString() ?? '',
              'answer': e['answer']?.toString() ?? '',
            },
          )
          .toList(),
      'lifestyle': {
        'drinking': _drinking,
        'smoking': _smoking,
        'exercise': _exercise,
        'religion': _religion,
      },
    };

    if (!mounted) return;
    Navigator.of(context, rootNavigator: true).pushNamed(
      RouteNames.profileSpecificDetail,
      arguments: ProfileCardArgs.preview(
        userId: kakaoUserId,
        onboardingOverride: previewOnboarding,
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  String _normalizeMajor(dynamic value) {
    final raw = value?.toString() ?? '';
    if (YonseiDepartments.majorLabels.containsKey(raw)) return raw;
    for (final entry in YonseiDepartments.majorLabels.entries) {
      if (entry.value == raw) return entry.key;
    }
    return raw;
  }

  String _labelize(String value) {
    for (final option in profileRelationshipOptions) {
      if (option.value == value) return option.label;
    }
    return YonseiDepartments.majorLabels[value] ?? value;
  }

  Future<void> _loadProfile() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    _currentUserId = kakaoUserId;

    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      return;
    }

    final data = await _userService.getUserProfile(kakaoUserId);
    final idealType = await _userService.getIdealType(kakaoUserId);

    final onboardingRaw = data?['onboarding'];
    final onboarding = onboardingRaw is Map
        ? Map<String, dynamic>.from(onboardingRaw)
        : <String, dynamic>{};
    final lockState = avatarLockStateFromUserProfile(
      data == null ? null : Map<String, dynamic>.from(data),
    );

    final avatarUrlsRaw = onboarding['avatarUrls'];
    final photoUrlsRaw = avatarUrlsRaw is List && avatarUrlsRaw.isNotEmpty
        ? avatarUrlsRaw
        : onboarding['photoUrls'];
    final interestsRaw = onboarding['interests'];
    final profileQaRaw = onboarding['profileQa'];
    final keywordsRaw = onboarding['keywords'];
    final lifestyleRaw = onboarding['lifestyle'];

    if (!mounted) return;

    setState(() {
      final photoUrls =
          lockState.isLocked && lockState.approvedAvatarUrl.isNotEmpty
          ? <String>[lockState.approvedAvatarUrl]
          : photoUrlsRaw is List
          ? photoUrlsRaw.whereType<String>().toList()
          : [];
      _avatarLocked = lockState.isLocked;
      _avatarSourceLocked =
          !lockState.isLocked &&
          (avatarSourceLockedFromUserProfile(
                data == null ? null : Map<String, dynamic>.from(data),
              ) ||
              photoUrls.any(
                (url) => AvatarSourcePhotoService.isQueuedSlotToken(url),
              ));
      _lockedApprovedAvatarUrl = lockState.approvedAvatarUrl;
      for (int i = 0; i < _photoSlots.length; i++) {
        _photoSlots[i] = i < photoUrls.length ? photoUrls[i] : null;
      }

      _selfIntroduction = onboarding['selfIntroduction']?.toString() ?? '';
      _nickname = onboarding['nickname']?.toString() ?? '';

      _age = _parseInt(onboarding['age'] ?? data?['age']);
      _gender =
          onboarding['gender']?.toString() ?? data?['gender']?.toString() ?? '';

      _interests = interestsRaw is List
          ? interestsRaw.map((e) => e.toString()).toList()
          : [];

      _keywords = keywordsRaw is List
          ? keywordsRaw.map((e) => e.toString()).toList()
          : [];

      _profileQa = profileQaRaw is List
          ? profileQaRaw
                .whereType<Map>()
                .map(
                  (e) => {
                    'question': e['question']?.toString() ?? '',
                    'answer': e['answer']?.toString() ?? '',
                  },
                )
                .toList()
          : [];

      _height = _parseInt(onboarding['height']);

      _grade = onboarding['grade']?.toString() ?? '';
      _isRa = onboarding['isRa'] == true;
      _relationship = onboarding['relationship']?.toString() ?? '';
      _mbti = onboarding['mbti']?.toString().toUpperCase() ?? '';
      _major = _normalizeMajor(onboarding['major']);
      _department = onboarding['department']?.toString() ?? '';

      if (lifestyleRaw is Map) {
        _drinking = lifestyleRaw['drinking']?.toString() ?? '';
        _smoking = lifestyleRaw['smoking']?.toString() ?? '';
        _exercise = lifestyleRaw['exercise']?.toString() ?? '';
        _religion = lifestyleRaw['religion']?.toString() ?? '';
      }

      final idealRaw = idealType ?? <String, dynamic>{};
      _hasIdealTypeData = idealType != null && idealType.isNotEmpty;
      _idealMinAge = _parseInt(idealRaw['minAge']);
      _idealMaxAge = _parseInt(idealRaw['maxAge']);
      _idealMinHeight = _parseInt(idealRaw['minHeight']);
      _idealMaxHeight = _parseInt(idealRaw['maxHeight']);
      _idealMbti = _asStringList(idealRaw['preferredMbti'])
          .map((value) => value.toUpperCase())
          .toList();
      _idealDepartments = _asStringList(idealRaw['preferredDepartments'])
          .map(_normalizeMajor)
          .toList();
      final preferredPersonalities = idealRaw['preferredPersonalities'];
      _idealPersonalityKeywords = preferredPersonalities is List
          ? preferredPersonalities.map((e) => e.toString()).toList()
          : [];
      final idealLifestyleRaw = idealRaw['preferredLifestyles'];
      if (idealLifestyleRaw is Map) {
        _idealDrinking = idealLifestyleRaw['drinking']?.toString() ?? '';
        _idealSmoking = idealLifestyleRaw['smoking']?.toString() ?? '';
        _idealExercise = idealLifestyleRaw['exercise']?.toString() ?? '';
        _idealReligion = idealLifestyleRaw['religion']?.toString() ?? '';
      }
      _idealTypeDirty = false;

      _isLoading = false;
    });
  }

  Future<void> _saveProfile() async {
    if (_isSaving) return;
    if (!_validateBeforeSave()) return;
    setState(() => _isSaving = true);

    try {
      final kakaoUserId =
          _currentUserId ?? await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인 정보가 없습니다.');
      }

      await _userService.saveOnboardingBasicInfo(
        kakaoUserId: kakaoUserId,
        basicInfo: {
          'nickname': _nickname.trim(),
          'selfIntroduction': _selfIntroduction.trim(),
          'height': _height,
          'grade': _nullableValue(_grade),
          'isRa': _isRa,
          'relationship': _nullableValue(_relationship),
          'mbti': _nullableValue(_mbti),
          'major': _major,
          'department': _nullableValue(_department),
          'lifestyle': {
            'drinking': _nullableValue(_drinking),
            'smoking': _nullableValue(_smoking),
            'exercise': _nullableValue(_exercise),
            'religion': _nullableValue(_religion),
          },
        },
      );

      // Interest and keyword lists are independent onboarding leaves. Keep
      // them on their dedicated write paths so editing one list cannot be
      // lost when another profile field is saved at the same time.
      await _userService.saveOnboardingInterests(
        kakaoUserId: kakaoUserId,
        interests: List<String>.unmodifiable(_interests),
      );
      await _userService.saveOnboardingKeywords(
        kakaoUserId: kakaoUserId,
        keywords: List<String>.unmodifiable(_keywords),
      );

      await _userService.saveOnboardingProfileQa(
        kakaoUserId: kakaoUserId,
        profileQa: _profileQa,
      );

      if (_hasIdealTypeData || _idealTypeDirty) {
        await _userService.saveIdealType(
          kakaoUserId: kakaoUserId,
          idealType: {
            'minAge': _idealMinAge,
            'maxAge': _idealMaxAge,
            'minHeight': _idealMinHeight,
            'maxHeight': _idealMaxHeight,
            'preferredMbti': List<String>.unmodifiable(_idealMbti),
            'preferredDepartments': List<String>.unmodifiable(
              _idealDepartments,
            ),
            'preferredPersonalities': List<String>.unmodifiable(
              _idealPersonalityKeywords,
            ),
            'preferredLifestyles': {
              'drinking': _nullableValue(_idealDrinking),
              'smoking': _nullableValue(_idealSmoking),
              'exercise': _nullableValue(_idealExercise),
              'religion': _nullableValue(_idealReligion),
            },
          },
        );
      }

      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showCupertinoDialog(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('저장 실패'),
          content: const Text('프로필 저장에 실패했어요. 잠시 후 다시 시도해주세요.'),
          actions: [
            CupertinoDialogAction(
              child: const Text('확인'),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  bool _validateBeforeSave() {
    String? message;
    final nickname = _nickname.trim();
    if (nickname.isEmpty) {
      message = '닉네임을 입력해주세요.';
    } else if (_height == null ||
        _height! < profileHeightMin ||
        _height! > profileHeightMax) {
      message = '키를 온보딩과 같은 범위로 선택해주세요.';
    } else if (_keywords.isEmpty) {
      message = '나를 표현하는 키워드를 1개 이상 선택해주세요.';
    } else if (!academicGradeOptions.contains(_grade)) {
      message = '학년을 선택해주세요.';
    } else if (!YonseiDepartments.majorLabels.containsKey(_major)) {
      message = '계열을 선택해주세요.';
    } else if (!YonseiDepartments.departmentsFor(_major).contains(_department)) {
      message = '계열에 맞는 학과를 선택해주세요.';
    } else if (!profileRelationshipOptions.any(
      (option) => option.value == _relationship,
    )) {
      message = '내가 찾는 관계를 선택해주세요.';
    } else if (!_isValidMbti(_mbti)) {
      message = 'MBTI를 선택해주세요.';
    }

    if (message == null) return true;
    showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        content: Text(message!),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
    return false;
  }

  bool _isValidMbti(String value) {
    if (value.length != profileMbtiDimensions.length) return false;
    for (var i = 0; i < profileMbtiDimensions.length; i++) {
      final dimension = profileMbtiDimensions[i];
      if (value[i] != dimension.first && value[i] != dimension.second) {
        return false;
      }
    }
    return true;
  }

  Future<void> _editSingleText({
    required String title,
    required String initial,
    required ValueChanged<String> onSaved,
    String placeholder = '',
    bool multiline = false,
    TextInputType? keyboardType,
    int? maxLength,
    int? maxLines,
  }) async {
    final controller = TextEditingController(text: initial);
    await showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: Text(title, style: const TextStyle(fontFamily: 'Pretendard')),
        content: Padding(
          padding: const EdgeInsets.only(top: 12),
          child: CupertinoTextField(
            controller: controller,
            placeholder: placeholder,
            maxLines: maxLines ?? (multiline ? 4 : 1),
            maxLength: maxLength,
            keyboardType: keyboardType,
            style: const TextStyle(fontFamily: 'Pretendard'),
            placeholderStyle: TextStyle(
              fontFamily: 'Pretendard',
              color: CupertinoColors.placeholderText,
            ),
          ),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('취소', style: TextStyle(fontFamily: 'Pretendard')),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              onSaved(controller.text.trim());
              Navigator.of(context).pop();
            },
            child: const Text('저장', style: TextStyle(fontFamily: 'Pretendard')),
          ),
        ],
      ),
    );
  }

  Future<void> _showMultiSelectSheet({
    required String title,
    required List<String> options,
    required List<String> selected,
    required int maxSelection,
    required ValueChanged<List<String>> onSaved,
    String Function(String value)? optionLabel,
  }) async {
    final selectedSet = selected.toSet();
    await _showCenteredSheet(
      title: title,
      onDone: () => onSaved(selectedSet.toList()),
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: options.map((opt) {
                final isSelected = selectedSet.contains(opt);
                return _SelectChip(
                  label: optionLabel?.call(opt) ?? opt,
                  isSelected: isSelected,
                  onTap: () {
                    setSheetState(() {
                      if (isSelected) {
                        selectedSet.remove(opt);
                      } else {
                        if (selectedSet.length >= maxSelection) return;
                        selectedSet.add(opt);
                      }
                    });
                  },
                );
              }).toList(),
            ),
          );
        },
      ),
    );
  }

  Future<void> _showInterestSheet() async {
    final selectedSet = _interests.toSet();
    await _showCenteredSheet(
      title: '관심사',
      onDone: () => setState(() => _interests = selectedSet.toList()),
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: _interestCategories.map((cat) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${cat.emoji} ${cat.title}',
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: cat.items.map((opt) {
                          final isSelected = selectedSet.contains(opt);
                          return _SelectChip(
                            label: opt,
                            isSelected: isSelected,
                            onTap: () {
                              setSheetState(() {
                                if (isSelected) {
                                  selectedSet.remove(opt);
                                } else {
                                  if (selectedSet.length >=
                                      maxProfileInterests) {
                                    return;
                                  }
                                  selectedSet.add(opt);
                                }
                              });
                            },
                          );
                        }).toList(),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          );
        },
      ),
    );
  }

  Future<void> _showSingleSelectSheet({
    required String title,
    required List<ProfileOption> options,
    required String current,
    required ValueChanged<String> onSaved,
  }) async {
    var selected = current;
    await _showCenteredSheet(
      title: title,
      onDone: () => onSaved(selected),
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: options.map((opt) {
                final isSelected = selected == opt.value;
                return _SelectChip(
                  label: opt.label,
                  isSelected: isSelected,
                  onTap: () => setSheetState(() {
                    selected = opt.value;
                  }),
                );
              }).toList(),
            ),
          );
        },
      ),
    );
  }

  Future<void> _showMbtiSheet() async {
    String e = _mbti.isNotEmpty ? _mbti[0] : 'E';
    String n = _mbti.length >= 2 ? _mbti[1] : 'N';
    String f = _mbti.length >= 3 ? _mbti[2] : 'F';
    String j = _mbti.length >= 4 ? _mbti[3] : 'J';

    await _showCenteredSheet(
      title: 'MBTI',
      onDone: () => setState(() => _mbti = '$e$n$f$j'),
      useFlexible: false,
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: SizedBox(
              height: 120,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _MbtiColumn(
                    top: profileMbtiDimensions[0].first,
                    bottom: profileMbtiDimensions[0].second,
                    selected: e,
                    onSelect: (v) => setSheetState(() => e = v),
                  ),
                  _MbtiColumn(
                    top: profileMbtiDimensions[1].first,
                    bottom: profileMbtiDimensions[1].second,
                    selected: n,
                    onSelect: (v) => setSheetState(() => n = v),
                  ),
                  _MbtiColumn(
                    top: profileMbtiDimensions[2].first,
                    bottom: profileMbtiDimensions[2].second,
                    selected: f,
                    onSelect: (v) => setSheetState(() => f = v),
                  ),
                  _MbtiColumn(
                    top: profileMbtiDimensions[3].first,
                    bottom: profileMbtiDimensions[3].second,
                    selected: j,
                    onSelect: (v) => setSheetState(() => j = v),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _showLifestyleSheet() async {
    var drinking = _drinking;
    var smoking = _smoking;
    var exercise = _exercise;
    var religion = _religion;
    await _showCenteredSheet(
      title: '라이프스타일',
      onDone: () => setState(() {
        _drinking = drinking;
        _smoking = smoking;
        _exercise = exercise;
        _religion = religion;
      }),
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _OptionSection(
                  title: '음주',
                  options: profileDrinkingOptions,
                  selected: drinking,
                  onSelect: (v) => setSheetState(() => drinking = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '흡연',
                  options: profileSmokingOptions,
                  selected: smoking,
                  onSelect: (v) => setSheetState(() => smoking = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '운동',
                  options: profileExerciseOptions,
                  selected: exercise,
                  onSelect: (v) => setSheetState(() => exercise = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '종교',
                  options: profileReligionOptions,
                  selected: religion,
                  onSelect: (v) => setSheetState(() => religion = v),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _showProfileQaSheet() async {
    final questions = profileQuestionPrompts;
    final knownQuestions = questions.toSet();
    final Map<String, TextEditingController> controllers = {
      for (final q in questions)
        q: TextEditingController(
          text: _profileQa
              .firstWhere(
                (e) => e['question'] == q,
                orElse: () => {'answer': ''},
              )['answer']
              ?.toString(),
        ),
    };

    await _showCenteredSheet(
      title: '프로필 문답',
      onDone: () {
        final next = <Map<String, String>>[];
        // Keep answers from older app versions whose prompt is no longer in
        // the active onboarding list. Known prompts are rebuilt below.
        next.addAll(
          _profileQa.where(
            (entry) =>
                !knownQuestions.contains(entry['question']) &&
                (entry['answer'] ?? '').trim().isNotEmpty,
          ),
        );
        for (final q in questions) {
          final ans = controllers[q]?.text.trim() ?? '';
          if (ans.isNotEmpty) {
            next.add({'question': q, 'answer': ans});
          }
        }
        setState(() => _profileQa = next);
      },
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: questions.map((q) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    q,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 8),
                  CupertinoTextField(
                    controller: controllers[q],
                    placeholder: '답변을 입력하세요 (최대 100자)',
                    maxLength: maxProfileQaAnswerLength,
                    maxLines: 4,
                    style: const TextStyle(fontFamily: 'Pretendard'),
                    placeholderStyle: TextStyle(
                      fontFamily: 'Pretendard',
                      color: CupertinoColors.placeholderText,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
    for (final controller in controllers.values) {
      controller.dispose();
    }
  }

  Future<void> _showHeightPicker() async {
    final values = List<int>.generate(
      profileHeightMax - profileHeightMin + 1,
      (i) => profileHeightMin + i,
    );
    int selected =
        _height != null &&
            _height! >= profileHeightMin &&
            _height! <= profileHeightMax
        ? _height!
        : 170;
    final controller = FixedExtentScrollController(
      initialItem: values.indexOf(selected),
    );

    await _showCenteredSheet(
      title: '키 선택',
      onDone: () => setState(() => _height = selected),
      child: SizedBox(
        height: 200,
        child: CupertinoPicker(
          scrollController: controller,
          itemExtent: 36,
          onSelectedItemChanged: (i) => selected = values[i],
          children: values.map((v) => Center(child: Text('$v cm'))).toList(),
        ),
      ),
    );
    controller.dispose();
  }

  Future<void> _showIdealHeightPicker() async {
    final values = List<int>.generate(
      profileHeightMax - profileHeightMin + 1,
      (i) => profileHeightMin + i,
    );
    var mode = _idealMinHeight != null && _idealMaxHeight == null
        ? 'max'
        : 'min';
    int? minHeight = _idealMinHeight;
    int? maxHeight = _idealMaxHeight;
    var current = mode == 'max'
        ? (maxHeight ?? minHeight ?? 170)
        : (minHeight ?? 170);
    final controller = FixedExtentScrollController(
      initialItem:
          current.clamp(profileHeightMin, profileHeightMax) - profileHeightMin,
    );

    await _showCenteredSheet(
      title: '이상형 키',
      useFlexible: false,
      onDone: () {
        if (minHeight != null && maxHeight == null) {
          maxHeight = minHeight;
        } else if (minHeight == null && maxHeight != null) {
          minHeight = maxHeight;
        }
        setState(() {
          _idealMinHeight = minHeight;
          _idealMaxHeight = maxHeight;
          _idealTypeDirty = true;
        });
      },
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          void changeMode(String nextMode) {
            setSheetState(() {
              mode = nextMode;
              current = mode == 'min'
                  ? (minHeight ?? current)
                  : (maxHeight ?? minHeight ?? current);
            });
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!controller.hasClients) return;
              controller.jumpToItem(
                current.clamp(profileHeightMin, profileHeightMax) -
                    profileHeightMin,
              );
            });
          }

          return SizedBox(
            width: double.infinity,
            height: 292,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _SelectChip(
                        label: minHeight == null ? '최소 키' : '최소 ${minHeight}cm',
                        isSelected: mode == 'min',
                        onTap: () => changeMode('min'),
                      ),
                      const SizedBox(width: 8),
                      _SelectChip(
                        label: maxHeight == null ? '최대 키' : '최대 ${maxHeight}cm',
                        isSelected: mode == 'max',
                        onTap: () => changeMode('max'),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: CupertinoPicker(
                    scrollController: controller,
                    itemExtent: 36,
                    onSelectedItemChanged: (index) {
                      setSheetState(() {
                        current = values[index];
                        if (mode == 'min') {
                          minHeight = current;
                          if (maxHeight != null && maxHeight! < current) {
                            maxHeight = current;
                          }
                        } else {
                          maxHeight = current < (minHeight ?? current)
                              ? minHeight
                              : current;
                        }
                      });
                    },
                    children: values
                        .map((value) => Center(child: Text('$value cm')))
                        .toList(),
                  ),
                ),
                CupertinoButton(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  onPressed: () {
                    setSheetState(() {
                      minHeight = null;
                      maxHeight = null;
                      mode = 'min';
                      current = 170;
                    });
                    controller.jumpToItem(170 - profileHeightMin);
                  },
                  child: const Text('상관없어요'),
                ),
              ],
            ),
          );
        },
      ),
    );
    controller.dispose();
  }

  Future<void> _showIdealAgeSheet() async {
    var values = RangeValues(
      (_idealMinAge ?? 23).toDouble(),
      (_idealMaxAge ?? 28).toDouble(),
    );
    var cleared = _idealMinAge == null && _idealMaxAge == null;

    await _showCenteredSheet(
      title: '이상형 나이대',
      useFlexible: false,
      onDone: () {
        setState(() {
          _idealMinAge = cleared ? null : values.start.round();
          _idealMaxAge = cleared ? null : values.end.round();
          _idealTypeDirty = true;
        });
      },
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          final theme = Theme.of(context).copyWith(
            sliderTheme: SliderThemeData(
              activeTrackColor: _AppColors.primary,
              inactiveTrackColor: const Color(0xFFE5E7EB),
              thumbColor: _AppColors.primary,
              overlayColor: _AppColors.primary.withValues(alpha: 0.1),
              trackHeight: 4,
              rangeThumbShape: const RoundRangeSliderThumbShape(
                enabledThumbRadius: 12,
                elevation: 4,
                pressedElevation: 6,
              ),
            ),
          );
          return SizedBox(
            width: double.infinity,
            height: 176,
            child: Column(
              children: [
                Material(
                  color: Colors.transparent,
                  child: Theme(
                    data: theme,
                    child: RangeSlider(
                      values: values,
                      min: profileAgeSliderMin,
                      max: profileAgeSliderMax,
                      divisions: profileAgeMax - profileAgeMin,
                      labels: RangeLabels(
                        '${values.start.round()}',
                        '${values.end.round()}',
                      ),
                      onChanged: (next) {
                        setSheetState(() {
                          values = next;
                          cleared = false;
                        });
                      },
                    ),
                  ),
                ),
                Text(
                  '${values.start.round()}세 - ${values.end.round()}세',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                CupertinoButton(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  onPressed: () => setSheetState(() => cleared = true),
                  child: const Text('상관없어요'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _showIdealMbtiSheet() async {
    final selected = <String?>[
      for (final dimension in profileMbtiDimensions)
        _idealMbti.contains(dimension.first)
            ? dimension.first
            : _idealMbti.contains(dimension.second)
            ? dimension.second
            : null,
    ];

    await _showCenteredSheet(
      title: '이상형 MBTI',
      onDone: () => setState(() {
        _idealMbti = selected.whereType<String>().toList();
        _idealTypeDirty = true;
      }),
      useFlexible: false,
      child: StatefulBuilder(
        builder: (context, setSheetState) => Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: SizedBox(
            height: 136,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (var i = 0; i < profileMbtiDimensions.length; i++)
                  _OptionalMbtiColumn(
                    top: profileMbtiDimensions[i].first,
                    bottom: profileMbtiDimensions[i].second,
                    selected: selected[i],
                    onSelect: (value) =>
                        setSheetState(() => selected[i] = value),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _showIdealDepartmentsSheet() async {
    await _showMultiSelectSheet(
      title: '이상형 계열',
      options: YonseiDepartments.majorLabels.keys.toList(),
      optionLabel: YonseiDepartments.labelFor,
      selected: _idealDepartments,
      maxSelection: YonseiDepartments.majorLabels.length,
      onSaved: (values) => setState(() {
        _idealDepartments = values;
        _idealTypeDirty = true;
      }),
    );
  }

  Future<void> _showIdealLifestyleSheet() async {
    var drinking = _idealDrinking;
    var smoking = _idealSmoking;
    var exercise = _idealExercise;
    var religion = _idealReligion;
    await _showCenteredSheet(
      title: '이상형 라이프스타일',
      onDone: () => setState(() {
        _idealDrinking = drinking;
        _idealSmoking = smoking;
        _idealExercise = exercise;
        _idealReligion = religion;
        _idealTypeDirty = true;
      }),
      child: StatefulBuilder(
        builder: (context, setSheetState) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _OptionSection(
                  title: '음주',
                  options: profileDrinkingOptions,
                  selected: drinking,
                  allowDeselect: true,
                  onSelect: (value) => setSheetState(() => drinking = value),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '흡연',
                  options: profileSmokingOptions,
                  selected: smoking,
                  allowDeselect: true,
                  onSelect: (value) => setSheetState(() => smoking = value),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '운동',
                  options: profileExerciseOptions,
                  selected: exercise,
                  allowDeselect: true,
                  onSelect: (value) => setSheetState(() => exercise = value),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '종교',
                  options: profileReligionOptions,
                  selected: religion,
                  allowDeselect: true,
                  onSelect: (value) => setSheetState(() => religion = value),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _showDepartmentPicker() async {
    if (_major.isEmpty) {
      await showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('계열을 먼저 선택해주세요'),
          content: const Text('계열을 선택하면 해당 계열의 학과를 고를 수 있어요.'),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
      return;
    }

    await _showSingleSelectSheet(
      title: '학과',
      options: YonseiDepartments.departmentsFor(_major)
          .map((department) => ProfileOption(department, department))
          .toList(),
      current: _department,
      onSaved: (value) => setState(() {
        _department = value;
      }),
    );
  }

  Future<void> _showCenteredSheet({
    required String title,
    required VoidCallback onDone,
    required Widget child,
    bool useFlexible = true,
  }) async {
    await showCupertinoDialog(
      context: context,
      builder: (context) {
        final size = MediaQuery.of(context).size;
        return Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: 360,
              maxHeight: size.height * 0.75,
            ),
            child: CupertinoPopupSurface(
              isSurfacePainted: true,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _SheetHeader(
                    title: title,
                    onClose: () => Navigator.of(context).pop(),
                    onDone: () {
                      onDone();
                      Navigator.of(context).pop();
                    },
                  ),
                  if (useFlexible) Flexible(child: child) else child,
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _showProfileAvatarDisplayOnlyDialog() {
    if (_avatarLocked) {
      _showLockedAvatarDialog();
      return;
    }
    if (_avatarSourceLocked ||
        _photoSlots.any(AvatarSourcePhotoService.isQueuedSlotToken)) {
      _showSourceLockedAvatarDialog();
      return;
    }
    showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('프로필 이미지 변경 불가'),
        content: const Text('프로필 이미지는 아바타 생성 화면에서만 등록할 수 있어요.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  void _showLockedAvatarDialog() {
    showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('아바타 변경 불가'),
        content: const Text(lockedAvatarMessage),
        actions: [
          CupertinoDialogAction(
            child: const Text('확인'),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  void _showSourceLockedAvatarDialog() {
    showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('아바타 생성 진행 중'),
        content: const Text(sourceLockedAvatarMessage),
        actions: [
          CupertinoDialogAction(
            child: const Text('확인'),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: Colors.white.withValues(alpha: 0.9),
        border: const Border(bottom: BorderSide(color: Color(0xFFF2F4F6))),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: const Icon(
            CupertinoIcons.clear,
            color: _AppColors.textMain,
            size: 24,
          ),
        ),
        middle: const Text(
          '프로필 수정',
          style: TextStyle(
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _isSaving ? null : _saveProfile,
          child: const Text(
            '저장',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w500,
              color: Color(0xFF6B7684),
            ),
          ),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: _isLoading
            ? const Center(child: CupertinoActivityIndicator())
            : Column(
                children: [
                  Container(
                    color: Colors.white,
                    child: Row(
                      children: [
                        Expanded(
                          child: Container(
                            decoration: const BoxDecoration(
                              border: Border(
                                bottom: BorderSide(
                                  color: _AppColors.primary,
                                  width: 2,
                                ),
                              ),
                            ),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            alignment: Alignment.center,
                            child: const Text(
                              '수정하기',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: _AppColors.primary,
                              ),
                            ),
                          ),
                        ),
                        Expanded(
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTap: _openPreview,
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              alignment: Alignment.center,
                              child: const Text(
                                '미리보기',
                                style: TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                  color: _AppColors.textSub,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 24,
                      ),
                      child: Column(
                        children: [
                          _PhotoSection(
                            photoUrls: _photoSlots,
                            isUploading: const <bool>[
                              false,
                              false,
                              false,
                              false,
                              false,
                              false,
                            ],
                            avatarLocked: _avatarLocked,
                            sourceLocked:
                                !_avatarLocked &&
                                (_avatarSourceLocked ||
                                    _photoSlots.any(
                                      AvatarSourcePhotoService
                                          .isQueuedSlotToken,
                                    )),
                            lockedApprovedAvatarUrl: _lockedApprovedAvatarUrl,
                            onAddPhoto: (_) =>
                                _showProfileAvatarDisplayOnlyDialog(),
                            onRemovePhoto: (_) =>
                                _showProfileAvatarDisplayOnlyDialog(),
                          ),
                          const SizedBox(height: 16),
                          _SelfIntroSection(
                            introduction: _selfIntroduction,
                            nickname: _nickname,
                            onTap: () => _editSingleText(
                              title: '자기소개',
                              initial: _selfIntroduction,
                              placeholder: '자기소개를 입력하세요',
                              multiline: true,
                              maxLength: maxSelfIntroductionLength,
                              maxLines: 8,
                              onSaved: (v) =>
                                  setState(() => _selfIntroduction = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _ProfileQuestionsSection(
                            profileQa: _profileQa,
                            onTap: _showProfileQaSheet,
                          ),
                          const SizedBox(height: 16),
                          _DetailInfoSection(
                            nickname: _nickname,
                            interests: _interests,
                            height: _height,
                            relationship: _labelize(_relationship),
                            onNicknameTap: () => _editSingleText(
                              title: '닉네임',
                              initial: _nickname,
                              placeholder: '닉네임을 입력하세요',
                              onSaved: (v) => setState(() => _nickname = v),
                            ),
                            onInterestsTap: _showInterestSheet,
                            onHeightTap: _showHeightPicker,
                            onRelationshipTap: () => _showSingleSelectSheet(
                              title: '내가 찾는 관계',
                              options: profileRelationshipOptions,
                              current: _relationship,
                              onSaved: (v) => setState(() => _relationship = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _BasicInfoSection(
                            mbti: _mbti,
                            major: _labelize(_major),
                            grade: _grade,
                            department: _department,
                            isRa: _isRa,
                            onMbtiTap: _showMbtiSheet,
                            onMajorTap: () => _showSingleSelectSheet(
                              title: '계열',
                              options: YonseiDepartments.majorLabels.entries
                                  .map(
                                    (entry) =>
                                        ProfileOption(entry.key, entry.value),
                                  )
                                  .toList(),
                              current: _major,
                              onSaved: (v) => setState(() {
                                _major = v;
                                if (!YonseiDepartments.departmentsFor(
                                  v,
                                ).contains(_department)) {
                                  _department = '';
                                }
                              }),
                            ),
                            onDepartmentTap: _showDepartmentPicker,
                            onGradeTap: () => _showSingleSelectSheet(
                              title: '학년',
                              options: academicGradeOptions
                                  .map((grade) => ProfileOption(grade, grade))
                                  .toList(),
                              current: _grade,
                              onSaved: (v) => setState(() => _grade = v),
                            ),
                            onRaTap: () => setState(() => _isRa = !_isRa),
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '키워드',
                            items: _keywords,
                            onTap: () => _showMultiSelectSheet(
                              title: '키워드',
                              options: profileKeywordOptions,
                              selected: _keywords,
                              maxSelection: maxProfileKeywords,
                              onSaved: (v) => setState(() => _keywords = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 키워드',
                            items: _idealPersonalityKeywords,
                            onTap: () => _showMultiSelectSheet(
                              title: '이상형 키워드',
                              options: profileKeywordOptions,
                              selected: _idealPersonalityKeywords,
                              maxSelection: maxProfileKeywords,
                              onSaved: (v) => setState(() {
                                _idealPersonalityKeywords = v;
                                _idealTypeDirty = true;
                              }),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _LifestyleSection(
                            drinking: _drinking,
                            smoking: _smoking,
                            exercise: _exercise,
                            religion: _religion,
                            onEdit: _showLifestyleSheet,
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 키',
                            items:
                                _idealMinHeight == null &&
                                    _idealMaxHeight == null
                                ? const []
                                : [
                                    '${_idealMinHeight ?? _idealMaxHeight} - '
                                        '${_idealMaxHeight ?? _idealMinHeight} cm',
                                  ],
                            onTap: _showIdealHeightPicker,
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 나이대',
                            items: _idealMinAge == null && _idealMaxAge == null
                                ? const []
                                : [
                                    '${_idealMinAge ?? _idealMaxAge} - '
                                        '${_idealMaxAge ?? _idealMinAge}세',
                                  ],
                            onTap: _showIdealAgeSheet,
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 MBTI',
                            items: _idealMbti,
                            onTap: _showIdealMbtiSheet,
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 계열',
                            items: _idealDepartments
                                .map(YonseiDepartments.labelFor)
                                .toList(),
                            onTap: _showIdealDepartmentsSheet,
                          ),
                          const SizedBox(height: 16),
                          _LifestyleSection(
                            title: '이상형 라이프스타일',
                            drinking: _idealDrinking,
                            smoking: _idealSmoking,
                            exercise: _idealExercise,
                            religion: _idealReligion,
                            onEdit: _showIdealLifestyleSheet,
                          ),
                          const SizedBox(height: 100),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _PhotoSection extends StatelessWidget {
  final List<String?> photoUrls;
  final List<bool> isUploading;
  final bool avatarLocked;
  final bool sourceLocked;
  final String lockedApprovedAvatarUrl;
  final void Function(int index)? onAddPhoto;
  final void Function(int index)? onRemovePhoto;

  const _PhotoSection({
    required this.photoUrls,
    required this.isUploading,
    required this.avatarLocked,
    required this.sourceLocked,
    required this.lockedApprovedAvatarUrl,
    this.onAddPhoto,
    this.onRemovePhoto,
  });

  @override
  Widget build(BuildContext context) {
    final photos = List<String?>.from(photoUrls);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: const [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '프로필 사진',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    '얼굴이 나온 사진 2장은 필수에요',
                    style: TextStyle(fontSize: 14, color: _AppColors.textSub),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          ProfilePhotoMosaic(
            gap: 8,
            featuredBadge: const _FeaturedPhotoBadge(),
            itemBuilder: (context, index) {
              final isLoading = isUploading.isNotEmpty
                  ? isUploading[index]
                  : false;
              if (photos[index] != null) {
                final lockedCell =
                    avatarLocked && photos[index] == lockedApprovedAvatarUrl;
                return _PhotoItem(
                  imageUrl: photos[index]!,
                  onRemove: (lockedCell || sourceLocked)
                      ? null
                      : () => onRemovePhoto?.call(index),
                  locked: lockedCell,
                );
              }
              return _AddPhotoButton(
                isLoading: isLoading,
                onTap: () => onAddPhoto?.call(index),
              );
            },
          ),
          const SizedBox(height: 12),
          const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                CupertinoIcons.info_circle,
                color: _AppColors.primary,
                size: 17,
              ),
              SizedBox(width: 7),
              Expanded(
                child: Text(
                  '아바타를 생성하는 사진으로, 가입 후 바꿀 수 없어요',
                  style: TextStyle(
                    fontSize: 13,
                    color: _AppColors.textSub,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (avatarLocked) ...[
            const Text(
              lockedAvatarNotice,
              style: TextStyle(
                fontSize: 13,
                color: _AppColors.textSub,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 16),
          ],
          if (!avatarLocked && sourceLocked) ...[
            const Text(
              sourceLockedAvatarMessage,
              style: TextStyle(
                fontSize: 13,
                color: _AppColors.textSub,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 16),
          ],
          GestureDetector(
            onTap: () {},
            child: Row(
              children: const [
                Text(
                  '사진 가이드 참고하기',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.primary,
                  ),
                ),
                Icon(Icons.chevron_right, size: 16, color: _AppColors.primary),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PhotoItem extends StatelessWidget {
  final String imageUrl;
  final VoidCallback? onRemove;
  final bool locked;

  const _PhotoItem({
    required this.imageUrl,
    this.onRemove,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    final isQueuedSourcePhoto = AvatarSourcePhotoService.isQueuedSlotToken(
      imageUrl,
    );
    return Stack(
      fit: StackFit.expand,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: isQueuedSourcePhoto
              ? Container(
                  color: _AppColors.placeholderBg,
                  child: const Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          CupertinoIcons.check_mark_circled_solid,
                          color: _AppColors.primary,
                          size: 30,
                        ),
                        SizedBox(height: 8),
                        Text(
                          'Avatar pending',
                          style: TextStyle(
                            fontSize: 13,
                            color: _AppColors.textSub,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              : Image.network(imageUrl, fit: BoxFit.cover),
        ),
        if (!locked && onRemove != null)
          Positioned(
            top: 4,
            right: 4,
            child: Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.5),
                shape: BoxShape.circle,
              ),
              child: GestureDetector(
                onTap: onRemove,
                child: const Icon(Icons.close, color: Colors.white, size: 12),
              ),
            ),
          ),
        if (locked)
          Positioned(
            right: 8,
            bottom: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(CupertinoIcons.lock_fill, size: 12, color: Colors.white),
                  SizedBox(width: 4),
                  Text(
                    '잠김',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _FeaturedPhotoBadge extends StatelessWidget {
  const _FeaturedPhotoBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: _AppColors.primary,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 2,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: const Text(
        '대표 사진',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
      ),
    );
  }
}

class _AddPhotoButton extends StatelessWidget {
  final bool isLoading;
  final VoidCallback? onTap;

  const _AddPhotoButton({this.isLoading = false, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFFF9FAFB),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE5E7EB), width: 2),
        ),
        child: isLoading
            ? const Center(child: CupertinoActivityIndicator())
            : const Icon(Icons.add_rounded, color: Color(0xFFD1D5DB), size: 32),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  final String title;
  final VoidCallback onClose;
  final VoidCallback onDone;

  const _SheetHeader({
    required this.title,
    required this.onClose,
    required this.onDone,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFFF2F4F6))),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onClose,
            child: const Text(
              '닫기',
              style: TextStyle(color: _AppColors.textSub),
            ),
          ),
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onDone,
            child: const Text(
              '완료',
              style: TextStyle(color: _AppColors.primary),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _SelectChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected
              ? _AppColors.primary.withValues(alpha: 0.1)
              : _AppColors.placeholderBg,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? _AppColors.primary : Colors.transparent,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: isSelected ? _AppColors.primary : _AppColors.textMain,
          ),
        ),
      ),
    );
  }
}

class _MbtiColumn extends StatelessWidget {
  final String top;
  final String bottom;
  final String selected;
  final ValueChanged<String> onSelect;

  const _MbtiColumn({
    required this.top,
    required this.bottom,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _SelectChip(
          label: top,
          isSelected: selected == top,
          onTap: () => onSelect(top),
        ),
        const SizedBox(height: 8),
        _SelectChip(
          label: bottom,
          isSelected: selected == bottom,
          onTap: () => onSelect(bottom),
        ),
      ],
    );
  }
}

class _OptionalMbtiColumn extends StatelessWidget {
  final String top;
  final String bottom;
  final String? selected;
  final ValueChanged<String?> onSelect;

  const _OptionalMbtiColumn({
    required this.top,
    required this.bottom,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _SelectChip(
          label: top,
          isSelected: selected == top,
          onTap: () => onSelect(selected == top ? null : top),
        ),
        const SizedBox(height: 8),
        _SelectChip(
          label: bottom,
          isSelected: selected == bottom,
          onTap: () => onSelect(selected == bottom ? null : bottom),
        ),
      ],
    );
  }
}

class _OptionSection extends StatelessWidget {
  final String title;
  final List<ProfileOption> options;
  final String selected;
  final bool allowDeselect;
  final ValueChanged<String> onSelect;

  const _OptionSection({
    required this.title,
    required this.options,
    required this.selected,
    this.allowDeselect = false,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: options.map((opt) {
            return _SelectChip(
              label: opt.label,
              isSelected: selected == opt.value,
              onTap: () => onSelect(
                allowDeselect && selected == opt.value ? '' : opt.value,
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}

class _SelfIntroSection extends StatelessWidget {
  final String introduction;
  final String nickname;
  final VoidCallback? onTap;

  const _SelfIntroSection({
    required this.introduction,
    required this.nickname,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final text = introduction.isEmpty
        ? '${nickname.isEmpty ? '아직' : nickname} 자기소개가 아직 없어요'
        : introduction;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '자기소개',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 16),
            Stack(
              children: [
                Container(
                  width: double.infinity,
                  constraints: const BoxConstraints(minHeight: 128),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _AppColors.placeholderBg,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    text,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.5,
                      color: _AppColors.textMain,
                    ),
                  ),
                ),
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: Text(
                    '${introduction.length}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: _AppColors.textSub,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              '자기소개 꿀팁',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileQuestionsSection extends StatelessWidget {
  final List<Map<String, String>> profileQa;
  final VoidCallback? onTap;

  const _ProfileQuestionsSection({required this.profileQa, this.onTap});

  @override
  Widget build(BuildContext context) {
    final hasQa = profileQa.isNotEmpty;
    final firstQa = hasQa ? profileQa.first : null;
    final question = firstQa?['question'] ?? '프로필 문답 선택하기';
    final answer = firstQa?['answer'] ?? '프로필 문답 작성하기';

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    const Text(
                      '프로필 문답',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textMain,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: _AppColors.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ],
                ),
                const Text(
                  '+10%',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF9FAFB),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          question,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          answer,
                          style: const TextStyle(
                            fontSize: 14,
                            color: _AppColors.textSub,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    width: 32,
                    height: 32,
                    decoration: const BoxDecoration(
                      color: _AppColors.primary,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.add, color: Colors.white, size: 20),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailInfoSection extends StatelessWidget {
  final String nickname;
  final List<String> interests;
  final int? height;
  final String relationship;
  final VoidCallback? onNicknameTap;
  final VoidCallback? onInterestsTap;
  final VoidCallback? onHeightTap;
  final VoidCallback? onRelationshipTap;

  const _DetailInfoSection({
    required this.nickname,
    required this.interests,
    required this.height,
    required this.relationship,
    this.onNicknameTap,
    this.onInterestsTap,
    this.onHeightTap,
    this.onRelationshipTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _DetailTile(
          title: '닉네임',
          content: nickname.isEmpty ? '아직 설정되지 않음' : nickname,
          icon: Icons.person_outline,
          onTap: onNicknameTap,
        ),
        const SizedBox(height: 16),
        _DetailTile(
          title: '관심사',
          content: interests.isEmpty ? '아직 설정되지 않음' : interests.join(', '),
          showIcon: false,
          onTap: onInterestsTap,
        ),
        const SizedBox(height: 16),
        _DetailTile(
          title: '키',
          content: height == null ? '아직 설정되지 않음' : '$height cm',
          icon: Icons.straighten,
          onTap: onHeightTap,
        ),
        const SizedBox(height: 16),
        _DetailTile(
          title: '내가 찾는 관계',
          content: relationship.isEmpty ? '아직 설정되지 않음' : relationship,
          emoji: '😍',
          icon: Icons.visibility,
          onTap: onRelationshipTap,
        ),
      ],
    );
  }
}

class _DetailTile extends StatelessWidget {
  final String title;
  final String content;
  final IconData? icon;
  final String? emoji;
  final bool showIcon;
  final VoidCallback? onTap;

  const _DetailTile({
    required this.title,
    required this.content,
    this.icon,
    this.emoji,
    this.showIcon = true,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              decoration: BoxDecoration(
                color: _AppColors.placeholderBg,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Row(
                      children: [
                        if (icon != null) ...[
                          Icon(icon, color: Colors.grey[400], size: 20),
                          const SizedBox(width: 8),
                        ],
                        Expanded(
                          child: Text(
                            content,
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                              color: _AppColors.textMain,
                            ),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Row(
                    children: [
                      if (emoji != null) ...[
                        Text(emoji!, style: const TextStyle(fontSize: 20)),
                        const SizedBox(width: 8),
                      ],
                      if (showIcon)
                        Icon(
                          Icons.chevron_right,
                          color: Colors.grey[400],
                          size: 20,
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BasicInfoSection extends StatelessWidget {
  final String mbti;
  final String major;
  final String grade;
  final String department;
  final bool isRa;
  final VoidCallback? onMbtiTap;
  final VoidCallback? onMajorTap;
  final VoidCallback? onGradeTap;
  final VoidCallback? onDepartmentTap;
  final VoidCallback? onRaTap;

  const _BasicInfoSection({
    required this.mbti,
    required this.major,
    required this.grade,
    required this.department,
    required this.isRa,
    this.onMbtiTap,
    this.onMajorTap,
    this.onGradeTap,
    this.onDepartmentTap,
    this.onRaTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '나에 대한 정보',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 12),
          _BasicInfoItem(
            icon: Icons.school_outlined,
            label: '학년',
            value: grade.isEmpty ? '아직 설정되지 않음' : grade,
            onTap: onGradeTap,
          ),
          const SizedBox(height: 8),
          _BasicInfoItem(
            icon: Icons.psychology,
            label: 'MBTI',
            value: mbti.isEmpty ? '아직 설정되지 않음' : mbti,
            onTap: onMbtiTap,
          ),
          const SizedBox(height: 8),
          _BasicInfoItem(
            icon: Icons.school,
            label: '계열',
            value: major.isEmpty ? '아직 설정되지 않음' : major,
            onTap: onMajorTap,
          ),
          const SizedBox(height: 8),
          _BasicInfoItem(
            icon: Icons.menu_book_outlined,
            label: '학과',
            value: department.isEmpty ? '아직 설정되지 않음' : department,
            onTap: onDepartmentTap,
          ),
          const SizedBox(height: 8),
          _BasicInfoItem(
            icon: Icons.badge_outlined,
            label: 'RA 여부',
            value: isRa ? '예' : '아니요',
            onTap: onRaTap,
          ),
        ],
      ),
    );
  }
}

class _BasicInfoItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback? onTap;

  const _BasicInfoItem({
    required this.icon,
    required this.label,
    required this.value,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        decoration: BoxDecoration(
          color: _AppColors.placeholderBg,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Icon(icon, color: Colors.grey[400], size: 20),
                const SizedBox(width: 12),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textMain,
                  ),
                ),
              ],
            ),
            Row(
              children: [
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 14,
                    color: _AppColors.textSub,
                  ),
                ),
                const SizedBox(width: 8),
                Icon(Icons.chevron_right, color: Colors.grey[400], size: 20),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SimpleListSection extends StatelessWidget {
  final String title;
  final List<String> items;
  final VoidCallback? onTap;

  const _SimpleListSection({
    required this.title,
    required this.items,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final content = items.isEmpty ? '아직 설정되지 않음' : items.join(', ');
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              decoration: BoxDecoration(
                color: _AppColors.placeholderBg,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      content,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.textMain,
                      ),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (onTap != null)
                    Icon(
                      Icons.chevron_right,
                      color: Colors.grey[400],
                      size: 20,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LifestyleSection extends StatelessWidget {
  final String title;
  final String drinking;
  final String smoking;
  final String exercise;
  final String religion;
  final VoidCallback? onEdit;

  const _LifestyleSection({
    this.title = '라이프스타일',
    required this.drinking,
    required this.smoking,
    required this.exercise,
    required this.religion,
    this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    String labelFor(String value, List<ProfileOption> options) {
      final match = options.where((o) => o.value == value).map((o) => o.label);
      return match.isNotEmpty ? match.first : value;
    }

    final text = [
      if (drinking.isNotEmpty)
        '음주: ${labelFor(drinking, profileDrinkingOptions)}',
      if (smoking.isNotEmpty) '흡연: ${labelFor(smoking, profileSmokingOptions)}',
      if (exercise.isNotEmpty)
        '운동: ${labelFor(exercise, profileExerciseOptions)}',
      if (religion.isNotEmpty)
        '종교: ${labelFor(religion, profileReligionOptions)}',
    ].join(', ');

    return GestureDetector(
      onTap: onEdit,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.03),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              decoration: BoxDecoration(
                color: _AppColors.placeholderBg,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      text.isEmpty ? '아직 설정되지 않음' : text,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.textMain,
                      ),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (onEdit != null)
                    Icon(
                      Icons.chevron_right,
                      color: Colors.grey[400],
                      size: 20,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
