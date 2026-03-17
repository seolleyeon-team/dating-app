import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
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

class _Option {
  final String value;
  final String label;
  const _Option(this.value, this.label);
}

class _InterestCategory {
  final String emoji;
  final String title;
  final List<String> items;

  const _InterestCategory({
    required this.emoji,
    required this.title,
    required this.items,
  });
}

const List<_InterestCategory> _interestCategories = [
  _InterestCategory(
    emoji: '🏠',
    title: 'Inside Activity',
    items: [
      '넷플릭스',
      '홈트',
      '드라마 정주행',
      '온라인 쇼핑',
      '식물 가꾸기',
      '보드게임',
      '명상',
      '요가',
      '사우나',
      '유튜브',
      '먹방',
      '도서관',
      '노래',
      '시',
      '문학',
      '댄스',
      '독서',
      '카공',
      '공부',
    ],
  ),
  _InterestCategory(
    emoji: '⛺',
    title: 'Outside Activity',
    items: [
      '한강에서 치맥',
      '빈티지 쇼핑',
      '동네 산책',
      '만화 카페',
      '방탈출',
      '카페 탐방',
      '맛집 투어',
      '브런치',
      '수제 맥주',
      '바',
      '자동차 극장',
      '콘서트',
      '아쿠아리움',
      '쇼핑',
      '전시회',
      '연극',
      '롤러 스케이트',
      '노래방',
      '야경 보기',
      '캠핑',
      '서핑',
      '낚시',
      '피크닉',
      '다이빙',
      '여행',
      '오락실',
      '노상',
      '새벽 라면',
      '바다 보기',
      '사진',
      '스케이트',
    ],
  ),
  _InterestCategory(
    emoji: '🍷',
    title: 'Eat & Drink',
    items: [
      '칵테일',
      '맥주',
      '빵',
      '양식',
      '중식',
      '일식',
      '분식',
      '디저트',
      '마라탕',
      '초밥',
      '회',
      '떡볶이',
      '피자',
      '햄버거',
      '치킨',
      '삼겹살',
      '카페',
      '와인',
      '위스키',
    ],
  ),
  _InterestCategory(
    emoji: '🎮',
    title: 'Game',
    items: [
      '리그 오브 레전드',
      '발로란트',
      '오버워치',
      '피파',
      '배그',
      '카트라이더',
      '메이플스토리',
      'FC온라인',
      '모바일 게임',
      '콘솔 게임',
      '보드게임',
    ],
  ),
  _InterestCategory(
    emoji: '🎵',
    title: 'Music',
    items: [
      '발라드',
      '힙합',
      'R&B',
      '인디',
      'K-POP',
      '클래식',
      'OST',
      '재즈',
      '락',
      '댄스',
      '밴드',
    ],
  ),
  _InterestCategory(
    emoji: '⚽',
    title: 'Sports',
    items: [
      '축구',
      '야구',
      '농구',
      '배구',
      '테니스',
      '배드민턴',
      '탁구',
      '골프',
      '헬스',
      '클라이밍',
      '러닝',
      '요가',
      '필라테스',
      '수영',
      '자전거',
    ],
  ),
  _InterestCategory(
    emoji: '🎬',
    title: 'Movie/Drama',
    items: ['영화', '드라마', '로맨스', '액션', '스릴러', '공포', '코미디', '다큐', '애니메이션'],
  ),
  _InterestCategory(
    emoji: '🧑‍🎨',
    title: 'Creative',
    items: ['그림', '사진', '영상', '글쓰기', '악기', '작곡', '공예', '캘리그래피'],
  ),
];

const List<String> _keywordOptions = [
  '친절한',
  '자신감 있는',
  '아담한',
  '듬직한',
  '잘 웃는',
  '자유분방한',
  '욕 안하는',
  '목소리 좋은',
  '또라이 같은',
  '먼저 말걸어주는',
  '옷 잘입는',
  '활발한',
  '조용한',
  '애교가 많은',
  '어른스러운',
  '열정적인',
  '차분한',
  '예의 바른',
  '재치있는',
  '진지한',
];

const List<String> _idealPersonalityOptions = _keywordOptions;

const List<_Option> _relationshipOptions = [
  _Option('serious', '진지한 연애를 원해요'),
  _Option('friend', '가볍게 알아가고 싶어요'),
  _Option('open', '열린 만남도 괜찮아요'),
];

const List<_Option> _majorOptions = [
  _Option('liberalArts', '문과 계열'),
  _Option('science', '이과 계열'),
  _Option('medical', '메디컬 계열'),
  _Option('artsSports', '예체능 계열'),
];

const List<_Option> _drinkingOptions = [
  _Option('none', '전혀 안 함'),
  _Option('sometimes', '가끔'),
  _Option('weekly1_2', '주 1-2회'),
  _Option('often', '자주'),
];

const List<_Option> _smokingOptions = [
  _Option('nonSmoker', '비흡연'),
  _Option('smoker', '흡연'),
  _Option('quitting', '금연 중'),
];

const List<_Option> _exerciseOptions = [
  _Option('daily', '매일 함'),
  _Option('sometimes', '가끔 함'),
  _Option('breathingOnly', '숨쉬기만 함'),
  _Option('mania', '운동 매니아'),
];

const List<_Option> _religionOptions = [
  _Option('none', '무교'),
  _Option('christianity', '기독교'),
  _Option('catholic', '천주교'),
  _Option('buddhism', '불교'),
  _Option('other', '기타'),
];

class ProfileEditScreen extends StatefulWidget {
  const ProfileEditScreen({super.key});

  @override
  State<ProfileEditScreen> createState() => _ProfileEditScreenState();
}

class _ProfileEditScreenState extends State<ProfileEditScreen> {
  final _userService = UserService();
  final _storageService = StorageService();
  final ImagePicker _imagePicker = ImagePicker();

  bool _isLoading = true;
  bool _isSaving = false;

  String? _currentUserId;
  int? _birthYear;

  final List<String?> _photoSlots = List<String?>.filled(6, null);
  final List<bool> _photoUploading = List<bool>.filled(6, false);

  String _selfIntroduction = '';
  List<Map<String, String>> _profileQa = [];
  List<String> _interests = [];
  List<String> _keywords = [];
  List<String> _idealPersonalityKeywords = [];

  int? _height;
  String _relationship = '';
  String _mbti = '';
  String _major = '';
  String _nickname = '';
  String _drinking = '';
  String _smoking = '';
  String _exercise = '';
  String _religion = '';

  Future<void> _openPreview() async {
    final kakaoUserId =
        _currentUserId ?? await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;

    final previewOnboarding = <String, dynamic>{
      'nickname': _nickname.trim(),
      'selfIntroduction': _selfIntroduction.trim(),
      'birthYear': _birthYear,
      'height': _height,
      'mbti': _mbti,
      'major': _major,
      'relationship': _relationship,
      'interests': List<String>.from(_interests),
      'keywords': List<String>.from(_keywords),
      'loveLanguages': const <String>[],
      'photoUrls': _photoSlots.whereType<String>().toList(),
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

  String _labelize(String value) {
    switch (value) {
      case 'serious':
        return '진지한 연애를 원해요';
      case 'friend':
        return '가볍게 알아가고 싶어요';
      case 'open':
        return '열린 만남도 괜찮아요';
      case 'liberalArts':
        return '문과 계열';
      case 'science':
        return '이과 계열';
      case 'medical':
        return '메디컬 계열';
      case 'artsSports':
        return '예체능 계열';
      case 'male':
        return '남성';
      case 'female':
        return '여성';
      case 'other':
        return '기타';
      default:
        return value;
    }
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

    final photoUrlsRaw = onboarding['photoUrls'];
    final interestsRaw = onboarding['interests'];
    final profileQaRaw = onboarding['profileQa'];
    final keywordsRaw = onboarding['keywords'];
    final lifestyleRaw = onboarding['lifestyle'];

    if (!mounted) return;

    setState(() {
      final photoUrls = photoUrlsRaw is List
          ? photoUrlsRaw.whereType<String>().toList()
          : [];
      for (int i = 0; i < _photoSlots.length; i++) {
        _photoSlots[i] = i < photoUrls.length ? photoUrls[i] : null;
      }

      _selfIntroduction = onboarding['selfIntroduction']?.toString() ?? '';
      _nickname = onboarding['nickname']?.toString() ?? '';

      final birthYearRaw = onboarding['birthYear'] ?? data?['birthYear'];
      if (birthYearRaw is num) {
        _birthYear = birthYearRaw.toInt();
      } else if (birthYearRaw != null) {
        _birthYear = int.tryParse(birthYearRaw.toString());
      } else {
        _birthYear = null;
      }

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

      final heightRaw = onboarding['height'];
      _height = heightRaw is num ? heightRaw.toInt() : null;

      _relationship = onboarding['relationship']?.toString() ?? '';
      _mbti = onboarding['mbti']?.toString() ?? '';
      _major = onboarding['major']?.toString() ?? '';

      if (lifestyleRaw is Map) {
        _drinking = lifestyleRaw['drinking']?.toString() ?? '';
        _smoking = lifestyleRaw['smoking']?.toString() ?? '';
        _exercise = lifestyleRaw['exercise']?.toString() ?? '';
        _religion = lifestyleRaw['religion']?.toString() ?? '';
      }

      final idealRaw = idealType ?? {};
      final preferredPersonalities = idealRaw['preferredPersonalities'];
      _idealPersonalityKeywords = preferredPersonalities is List
          ? preferredPersonalities.map((e) => e.toString()).toList()
          : [];

      _isLoading = false;
    });
  }

  Future<void> _saveProfile() async {
    if (_isSaving) return;
    setState(() => _isSaving = true);

    try {
      final kakaoUserId =
          _currentUserId ?? await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('로그인 정보가 없습니다.');
      }

      final photoUrls = _photoSlots.whereType<String>().toList();
      if (photoUrls.length < 2) {
        throw Exception('프로필 사진은 최소 2장 이상 등록해야 합니다.');
      }

      await _userService.saveOnboardingBasicInfo(
        kakaoUserId: kakaoUserId,
        basicInfo: {
          'nickname': _nickname.trim(),
          'selfIntroduction': _selfIntroduction.trim(),
          'interests': _interests.map((e) => e.toString()).toList(),
          'height': _height,
          'relationship': _relationship,
          'mbti': _mbti.trim(),
          'major': _major,
          'lifestyle': {
            'drinking': _drinking,
            'smoking': _smoking,
            'exercise': _exercise,
            'religion': _religion,
          },
          'keywords': _keywords.map((e) => e.toString()).toList(),
        },
      );

      await _userService.saveOnboardingPhotos(
        kakaoUserId: kakaoUserId,
        photoUrls: photoUrls,
      );

      if (_profileQa.isNotEmpty) {
        await _userService.saveOnboardingProfileQa(
          kakaoUserId: kakaoUserId,
          profileQa: _profileQa,
        );
      }

      if (_idealPersonalityKeywords.isNotEmpty) {
        await _userService.updateIdealTypeField(
          kakaoUserId: kakaoUserId,
          fieldName: 'preferredPersonalities',
          value: _idealPersonalityKeywords,
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
          content: Text(e.toString()),
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

  Future<void> _editSingleText({
    required String title,
    required String initial,
    required ValueChanged<String> onSaved,
    String placeholder = '',
    bool multiline = false,
    TextInputType? keyboardType,
  }) async {
    final controller = TextEditingController(text: initial);
    await showCupertinoDialog(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: Text(title),
        content: Padding(
          padding: const EdgeInsets.only(top: 12),
          child: CupertinoTextField(
            controller: controller,
            placeholder: placeholder,
            maxLines: multiline ? 4 : 1,
            keyboardType: keyboardType,
          ),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              onSaved(controller.text.trim());
              Navigator.of(context).pop();
            },
            child: const Text('저장'),
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
                  label: opt,
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
                                  if (selectedSet.length >= 10) return;
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
    required List<_Option> options,
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
    String e = _mbti.length >= 1 ? _mbti[0] : 'E';
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
                    top: 'E',
                    bottom: 'I',
                    selected: e,
                    onSelect: (v) => setSheetState(() => e = v),
                  ),
                  _MbtiColumn(
                    top: 'N',
                    bottom: 'S',
                    selected: n,
                    onSelect: (v) => setSheetState(() => n = v),
                  ),
                  _MbtiColumn(
                    top: 'F',
                    bottom: 'T',
                    selected: f,
                    onSelect: (v) => setSheetState(() => f = v),
                  ),
                  _MbtiColumn(
                    top: 'J',
                    bottom: 'P',
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
                  options: _drinkingOptions,
                  selected: drinking,
                  onSelect: (v) => setSheetState(() => drinking = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '흡연',
                  options: _smokingOptions,
                  selected: smoking,
                  onSelect: (v) => setSheetState(() => smoking = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '운동',
                  options: _exerciseOptions,
                  selected: exercise,
                  onSelect: (v) => setSheetState(() => exercise = v),
                ),
                const SizedBox(height: 12),
                _OptionSection(
                  title: '종교',
                  options: _religionOptions,
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
    final questions = [
      '주말에 보통 뭐 해요?',
      '가장 좋아하는 음식은?',
      '나의 힐링 포인트는?',
      '기억에 남는 여행지는?',
      '내 이상형에 가까운 사람은?',
    ];
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
                    maxLength: 100,
                    maxLines: 2,
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Future<void> _showHeightPicker() async {
    final values = List<int>.generate(56, (i) => 145 + i);
    int selected = _height != null && _height! >= 145 && _height! <= 200
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

  Future<void> _addPhoto(int index) async {
    HapticFeedback.lightImpact();
    final pickedFile = await _imagePicker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 88,
    );
    if (pickedFile == null) return;

    setState(() => _photoUploading[index] = true);

    try {
      final kakaoUserId =
          _currentUserId ?? await _storageService.getKakaoUserId();
      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw Exception('사용자 정보를 찾을 수 없습니다.');
      }

      final extension = pickedFile.path.split('.').last.isNotEmpty
          ? pickedFile.path.split('.').last
          : 'jpg';
      final fileName =
          '${DateTime.now().millisecondsSinceEpoch}_slot$index.$extension';
      final ref = FirebaseStorage.instance.ref().child(
        'users/$kakaoUserId/onboarding/photos/$fileName',
      );

      final metadata = SettableMetadata(contentType: 'image/$extension');
      final bytes = await pickedFile.readAsBytes();
      await ref.putData(bytes, metadata);
      final url = await ref.getDownloadURL();

      if (!mounted) return;
      setState(() => _photoSlots[index] = url);
    } catch (e) {
      if (!mounted) return;
      showCupertinoDialog(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('사진 업로드 실패'),
          content: Text(e.toString()),
          actions: [
            CupertinoDialogAction(
              child: const Text('확인'),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() => _photoUploading[index] = false);
    }
  }

  Future<void> _removePhoto(int index) async {
    HapticFeedback.selectionClick();
    final url = _photoSlots[index];
    setState(() => _photoSlots[index] = null);

    if (url != null && url.isNotEmpty) {
      try {
        final ref = FirebaseStorage.instance.refFromURL(url);
        await ref.delete();
      } catch (_) {}
    }

    final kakaoUserId =
        _currentUserId ?? await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final photoUrls = _photoSlots.whereType<String>().toList();
    await _userService.saveOnboardingPhotos(
      kakaoUserId: kakaoUserId,
      photoUrls: photoUrls,
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
                            isUploading: _photoUploading,
                            onAddPhoto: _addPhoto,
                            onRemovePhoto: _removePhoto,
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
                            interests: _interests,
                            height: _height,
                            relationship: _labelize(_relationship),
                            onInterestsTap: _showInterestSheet,
                            onHeightTap: _showHeightPicker,
                            onRelationshipTap: () => _showSingleSelectSheet(
                              title: '내가 찾는 관계',
                              options: _relationshipOptions,
                              current: _relationship,
                              onSaved: (v) => setState(() => _relationship = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _BasicInfoSection(
                            mbti: _mbti,
                            major: _labelize(_major),
                            onMbtiTap: _showMbtiSheet,
                            onMajorTap: () => _showSingleSelectSheet(
                              title: '전공',
                              options: _majorOptions,
                              current: _major,
                              onSaved: (v) => setState(() => _major = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '키워드',
                            items: _keywords,
                            onTap: () => _showMultiSelectSheet(
                              title: '키워드',
                              options: _keywordOptions,
                              selected: _keywords,
                              maxSelection: 8,
                              onSaved: (v) => setState(() => _keywords = v),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _SimpleListSection(
                            title: '이상형 키워드',
                            items: _idealPersonalityKeywords,
                            onTap: () => _showMultiSelectSheet(
                              title: '이상형 키워드',
                              options: _idealPersonalityOptions,
                              selected: _idealPersonalityKeywords,
                              maxSelection: 8,
                              onSaved: (v) =>
                                  setState(() => _idealPersonalityKeywords = v),
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
  final void Function(int index)? onAddPhoto;
  final void Function(int index)? onRemovePhoto;

  const _PhotoSection({
    required this.photoUrls,
    required this.isUploading,
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
                    '얼굴이 나온 사진 3장은 필수에요',
                    style: TextStyle(fontSize: 14, color: _AppColors.textSub),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final gap = 8.0;

              Widget buildCell(int index) {
                final isLoading = isUploading.isNotEmpty
                    ? isUploading[index]
                    : false;
                if (photos[index] != null) {
                  return _PhotoItem(
                    imageUrl: photos[index]!,
                    onRemove: () => onRemovePhoto?.call(index),
                    showMainLabel: index == 0,
                  );
                }
                return _AddPhotoButton(
                  isLoading: isLoading,
                  onTap: () => onAddPhoto?.call(index),
                );
              }

              return Column(
                children: List.generate(3, (row) {
                  final leftIndex = row * 2;
                  final rightIndex = row * 2 + 1;
                  return Padding(
                    padding: EdgeInsets.only(bottom: row == 2 ? 0 : gap),
                    child: Row(
                      children: [
                        Expanded(
                          child: AspectRatio(
                            aspectRatio: 3 / 4,
                            child: buildCell(leftIndex),
                          ),
                        ),
                        SizedBox(width: gap),
                        Expanded(
                          child: AspectRatio(
                            aspectRatio: 3 / 4,
                            child: buildCell(rightIndex),
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              );
            },
          ),
          const SizedBox(height: 16),
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
  final bool showMainLabel;

  const _PhotoItem({
    required this.imageUrl,
    this.onRemove,
    this.showMainLabel = false,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.network(imageUrl, fit: BoxFit.cover),
        ),
        if (showMainLabel)
          Positioned(
            top: 8,
            left: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text(
                '메인',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ),
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
      ],
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

class _OptionSection extends StatelessWidget {
  final String title;
  final List<_Option> options;
  final String selected;
  final ValueChanged<String> onSelect;

  const _OptionSection({
    required this.title,
    required this.options,
    required this.selected,
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
              onTap: () => onSelect(opt.value),
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
  final List<String> interests;
  final int? height;
  final String relationship;
  final VoidCallback? onInterestsTap;
  final VoidCallback? onHeightTap;
  final VoidCallback? onRelationshipTap;

  const _DetailInfoSection({
    required this.interests,
    required this.height,
    required this.relationship,
    this.onInterestsTap,
    this.onHeightTap,
    this.onRelationshipTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
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
  final VoidCallback? onMbtiTap;
  final VoidCallback? onMajorTap;

  const _BasicInfoSection({
    required this.mbti,
    required this.major,
    this.onMbtiTap,
    this.onMajorTap,
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
          const _BasicInfoItem(
            icon: Icons.nightlight_round,
            label: '별자리',
            value: '준비 중',
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
            label: '전공',
            value: major.isEmpty ? '아직 설정되지 않음' : major,
            onTap: onMajorTap,
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
  final String drinking;
  final String smoking;
  final String exercise;
  final String religion;
  final VoidCallback? onEdit;

  const _LifestyleSection({
    required this.drinking,
    required this.smoking,
    required this.exercise,
    required this.religion,
    this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    String labelFor(String value, List<_Option> options) {
      final match = options.where((o) => o.value == value).map((o) => o.label);
      return match.isNotEmpty ? match.first : value;
    }

    final text = [
      if (drinking.isNotEmpty) '음주: ${labelFor(drinking, _drinkingOptions)}',
      if (smoking.isNotEmpty) '흡연: ${labelFor(smoking, _smokingOptions)}',
      if (exercise.isNotEmpty) '운동: ${labelFor(exercise, _exerciseOptions)}',
      if (religion.isNotEmpty) '종교: ${labelFor(religion, _religionOptions)}',
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
            const Text(
              '라이프스타일',
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
