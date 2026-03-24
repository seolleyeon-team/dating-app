import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

class IssueReportScreen extends StatefulWidget {
  const IssueReportScreen({super.key, this.onSubmit});

  /// 나중에 Firestore 저장 로직 연결할 때 사용
  /// return true  -> 성공
  /// return false -> 실패
  final Future<bool> Function({
    required String category,
    required String content,
    required bool allowContact,
  })?
  onSubmit;

  @override
  State<IssueReportScreen> createState() => _IssueReportScreenState();
}

class _IssueReportScreenState extends State<IssueReportScreen> {
  final TextEditingController _contentController = TextEditingController();

  final List<String> _categories = const [
    '앱 오류/멈춤',
    '채팅',
    '알림',
    '프로필',
    '매칭',
    '결제/하트',
    '커뮤니티',
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
    if (mounted) setState(() {});
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
        await Future.delayed(const Duration(milliseconds: 500));
      }

      if (!mounted) return;

      if (success) {
        await showCupertinoDialog(
          context: context,
          builder: (ctx) => CupertinoAlertDialog(
            title: const Text('접수 완료'),
            content: const Text('문제가 접수되었습니다.\n빠르게 확인해볼게요.'),
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
        await _showErrorDialog('문제를 접수하지 못했어요.\n잠시 후 다시 시도해주세요.');
      }
    } catch (e) {
      if (!mounted) return;
      await _showErrorDialog('문제를 접수하지 못했어요.\n잠시 후 다시 시도해주세요.');
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
      backgroundColor: _IssueColors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _IssueColors.background.withValues(alpha: 0.96),
        border: null,
        middle: const Text(
          '문제 신고',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: _IssueColors.textMain,
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
            color: _IssueColors.textMain,
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
              _HeaderCard(),
              const SizedBox(height: 20),
              _SectionTitle(title: '어떤 문제인가요?'),
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
              _SectionTitle(title: '자세히 알려주세요'),
              const SizedBox(height: 10),
              _InputCard(
                child: CupertinoTextField(
                  controller: _contentController,
                  minLines: 7,
                  maxLines: 10,
                  padding: const EdgeInsets.all(16),
                  placeholder:
                      '어떤 화면에서 어떤 문제가 있었는지 적어주세요.\n예: 채팅방에 들어가면 메시지가 늦게 보여요.',
                  placeholderStyle: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    color: _IssueColors.textHint,
                    fontSize: 15,
                    height: 1.45,
                  ),
                  style: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    color: _IssueColors.textMain,
                    fontSize: 15,
                    height: 1.5,
                  ),
                  decoration: null,
                ),
              ),
              const SizedBox(height: 24),
              _SectionTitle(title: '추가 설정'),
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
                              color: _IssueColors.textMain,
                            ),
                          ),
                          SizedBox(height: 6),
                          Text(
                            '문제 재현이나 확인을 위해 운영팀이 연락할 수 있어요.',
                            style: TextStyle(
                              fontSize: 13,
                              height: 1.4,
                              color: _IssueColors.textSub,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    CupertinoSwitch(
                      value: _allowContact,
                      activeTrackColor: _IssueColors.primary,
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
                          ? _IssueColors.primary
                          : _IssueColors.disabled,
                      borderRadius: BorderRadius.circular(18),
                      boxShadow: _canSubmit
                          ? [
                              BoxShadow(
                                color: _IssueColors.primary.withValues(
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
                            '문제 신고 접수하기',
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
                  '신고 내용은 서비스 개선을 위해 검토됩니다.',
                  style: TextStyle(fontSize: 12, color: _IssueColors.textSub),
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
        border: Border.all(color: _IssueColors.border),
        boxShadow: [
          BoxShadow(
            color: _IssueColors.primary.withValues(alpha: 0.08),
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
                CupertinoIcons.exclamationmark_bubble_fill,
                size: 20,
                color: _IssueColors.primary,
              ),
              SizedBox(width: 8),
              Text(
                '앱 이용 중 불편하셨나요?',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: _IssueColors.textMain,
                ),
              ),
            ],
          ),
          SizedBox(height: 10),
          Text(
            '오류, 불편사항, 개선이 필요한 점을 알려주세요.\n빠르게 확인 후 더 나은 앱으로 개선할게요.',
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: _IssueColors.textSub,
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
        color: _IssueColors.textMain,
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
                  ? _IssueColors.primary.withValues(alpha: 0.12)
                  : CupertinoColors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: isSelected ? _IssueColors.primary : _IssueColors.border,
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
                    ? _IssueColors.primary
                    : _IssueColors.textMain,
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
        border: Border.all(color: _IssueColors.border),
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
        border: Border.all(color: _IssueColors.border),
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

class _IssueColors {
  static const Color primary = Color(0xFFFF5A7E);
  static const Color background = Color(0xFFFFF7F9);
  static const Color textMain = Color(0xFF1E1A1C);
  static const Color textSub = Color(0xFF6A6367);
  static const Color textHint = Color(0xFFA39AA0);
  static const Color border = Color(0xFFF0DDE4);
  static const Color disabled = Color(0xFFE5C7D1);
}
