import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

class InquiryScreen extends StatefulWidget {
  const InquiryScreen({super.key, this.onSubmit});

  /// return true  -> 성공
  /// return false -> 실패
  final Future<bool> Function({
    required String category,
    required String content,
    required bool allowContact,
  })?
  onSubmit;

  @override
  State<InquiryScreen> createState() => _InquiryScreenState();
}

class _InquiryScreenState extends State<InquiryScreen> {
  final TextEditingController _contentController = TextEditingController();

  final List<String> _categories = const [
    '계정/로그인',
    '프로필',
    '매칭',
    '채팅',
    '결제/하트',
    '신고/차단',
    '대나무숲',
    '기타',
  ];

  String? _selectedCategory;
  bool _allowContact = false;
  bool _isSubmitting = false;

  bool get _canSubmit {
    return _selectedCategory != null &&
        _contentController.text.trim().isNotEmpty &&
        !_isSubmitting;
  }

  @override
  void initState() {
    super.initState();
    _contentController.addListener(_refresh);
  }

  @override
  void dispose() {
    _contentController.removeListener(_refresh);
    _contentController.dispose();
    super.dispose();
  }

  void _refresh() {
    if (mounted) {
      setState(() {});
    }
  }

  Future<void> _submit() async {
    if (!_canSubmit) return;

    HapticFeedback.mediumImpact();

    final category = _selectedCategory!;
    final content = _contentController.text.trim();
    final allowContact = _allowContact;

    setState(() {
      _isSubmitting = true;
    });

    try {
      bool success = true;

      if (widget.onSubmit != null) {
        success = await widget.onSubmit!(
          category: category,
          content: content,
          allowContact: allowContact,
        );
      } else {
        await Future.delayed(const Duration(milliseconds: 400));
      }

      if (!mounted) return;

      if (success) {
        await showCupertinoDialog(
          context: context,
          builder: (ctx) => CupertinoAlertDialog(
            title: const Text('접수 완료'),
            content: const Text('문의가 접수되었습니다.\n확인 후 답변드릴게요.'),
            actions: [
              CupertinoDialogAction(
                isDefaultAction: true,
                onPressed: () => Navigator.pop(ctx),
                child: const Text('확인'),
              ),
            ],
          ),
        );

        if (!mounted) return;
        Navigator.of(context).pop(true);
      } else {
        await _showErrorDialog('문의를 접수하지 못했어요.\n잠시 후 다시 시도해주세요.');
      }
    } catch (_) {
      if (!mounted) return;
      await _showErrorDialog('문의를 접수하지 못했어요.\n잠시 후 다시 시도해주세요.');
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  Future<void> _showErrorDialog(String message) async {
    await showCupertinoDialog(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text('접수 실패'),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.pop(ctx),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _InquiryColors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _InquiryColors.background.withValues(alpha: 0.96),
        border: null,
        middle: const Text(
          '문의하기',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: _InquiryColors.textMain,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pop();
          },
          child: const Icon(
            CupertinoIcons.back,
            color: _InquiryColors.textMain,
            size: 26,
          ),
        ),
      ),
      child: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.fromLTRB(20, 20, 20, bottomPadding + 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _HeaderCard(),
              const SizedBox(height: 20),
              const _SectionTitle(title: '어떤 문의인가요?'),
              const SizedBox(height: 10),
              _CategorySelector(
                categories: _categories,
                selected: _selectedCategory,
                onSelected: (value) {
                  HapticFeedback.selectionClick();
                  setState(() {
                    _selectedCategory = value;
                  });
                },
              ),
              const SizedBox(height: 24),
              const _SectionTitle(title: '자세히 알려주세요'),
              const SizedBox(height: 10),
              const _SectionDescription(text: '문의 상황이나 궁금한 점을 최대한 자세히 적어주세요.'),
              const SizedBox(height: 10),
              _InputCard(
                child: CupertinoTextField(
                  controller: _contentController,
                  minLines: 7,
                  maxLines: 10,
                  padding: const EdgeInsets.all(16),
                  placeholder:
                      '예: 상대방이 보낸 하트는 어디에서 확인할 수 있나요?\n예: 매칭된 상대와 대화를 시작하려면 어떻게 하나요?\n예: 탈퇴하면 기존 채팅이나 정보는 어떻게 되나요?',
                  placeholderStyle: const TextStyle(
                    fontFamily: 'Pretendard',
                    color: _InquiryColors.textHint,
                    fontSize: 15,
                    height: 1.45,
                  ),
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    color: _InquiryColors.textMain,
                    fontSize: 15,
                    height: 1.5,
                  ),
                  decoration: null,
                ),
              ),
              const SizedBox(height: 24),
              const _SectionTitle(title: '추가 설정'),
              const SizedBox(height: 10),
              _OptionCard(
                child: Row(
                  children: [
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '추가 확인이 필요할 때 연락받기',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: _InquiryColors.textMain,
                            ),
                          ),
                          SizedBox(height: 6),
                          Text(
                            '문의 해결을 위해 운영팀이 추가로 연락할 수 있어요.',
                            style: TextStyle(
                              fontSize: 13,
                              height: 1.4,
                              color: _InquiryColors.textSub,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    CupertinoSwitch(
                      value: _allowContact,
                      activeTrackColor: _InquiryColors.primary,
                      onChanged: (value) {
                        HapticFeedback.selectionClick();
                        setState(() {
                          _allowContact = value;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: _canSubmit ? _submit : null,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    height: 56,
                    decoration: BoxDecoration(
                      color: _canSubmit
                          ? _InquiryColors.primary
                          : _InquiryColors.disabled,
                      borderRadius: BorderRadius.circular(18),
                      boxShadow: _canSubmit
                          ? [
                              BoxShadow(
                                color: _InquiryColors.primary.withValues(
                                  alpha: 0.28,
                                ),
                                blurRadius: 18,
                                offset: const Offset(0, 8),
                              ),
                            ]
                          : [],
                    ),
                    alignment: Alignment.center,
                    child: _isSubmitting
                        ? const CupertinoActivityIndicator(
                            color: CupertinoColors.white,
                          )
                        : const Text(
                            '문의 접수하기',
                            style: TextStyle(
                              color: CupertinoColors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              const Center(
                child: Text(
                  '문의 내용은 서비스 운영 및 안내를 위해 검토됩니다.',
                  style: TextStyle(fontSize: 12, color: _InquiryColors.textSub),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HeaderCard extends StatelessWidget {
  const _HeaderCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFFFF5F7), Color(0xFFFFFBFC)],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: _InquiryColors.border),
        boxShadow: [
          BoxShadow(
            color: _InquiryColors.primary.withValues(alpha: 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.chat_bubble_2_fill,
                size: 20,
                color: _InquiryColors.primary,
              ),
              SizedBox(width: 8),
              Text(
                '궁금한 점이 있으신가요?',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: _InquiryColors.textMain,
                ),
              ),
            ],
          ),
          SizedBox(height: 10),
          Text(
            '앱 이용 중 궁금한 점이나 도움이 필요한 내용을 남겨주세요.\n확인 후 답변드릴게요.',
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: _InquiryColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w700,
        color: _InquiryColors.textMain,
      ),
    );
  }
}

class _SectionDescription extends StatelessWidget {
  const _SectionDescription({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 13,
        height: 1.4,
        color: _InquiryColors.textSub,
      ),
    );
  }
}

class _CategorySelector extends StatelessWidget {
  const _CategorySelector({
    required this.categories,
    required this.selected,
    required this.onSelected,
  });

  final List<String> categories;
  final String? selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: categories.map((category) {
        final isSelected = selected == category;

        return GestureDetector(
          onTap: () => onSelected(category),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: isSelected
                  ? _InquiryColors.primary.withValues(alpha: 0.12)
                  : CupertinoColors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: isSelected
                    ? _InquiryColors.primary
                    : _InquiryColors.border,
                width: isSelected ? 1.4 : 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.03),
                  blurRadius: 8,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Text(
              category,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: isSelected
                    ? _InquiryColors.primary
                    : _InquiryColors.textMain,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _InputCard extends StatelessWidget {
  const _InputCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _InquiryColors.border),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _OptionCard extends StatelessWidget {
  const _OptionCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _InquiryColors.border),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _InquiryColors {
  static const Color primary = Color(0xFFFF5A7E);
  static const Color background = Color(0xFFFFF7F9);
  static const Color textMain = Color(0xFF1E1A1C);
  static const Color textSub = Color(0xFF6A6367);
  static const Color textHint = Color(0xFFA39AA0);
  static const Color border = Color(0xFFF0DDE4);
  static const Color disabled = Color(0xFFE5C7D1);
}
