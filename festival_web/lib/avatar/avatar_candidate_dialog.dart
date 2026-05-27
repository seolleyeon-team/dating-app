import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'avatar_generation_models.dart';

class AvatarCandidateSelectionDialog extends StatefulWidget {
  const AvatarCandidateSelectionDialog({
    super.key,
    required this.candidates,
    required this.approving,
    required this.onApprove,
  });

  final List<AvatarCandidate> candidates;
  final bool approving;
  final ValueChanged<String> onApprove;

  @override
  State<AvatarCandidateSelectionDialog> createState() =>
      _AvatarCandidateSelectionDialogState();
}

class _AvatarCandidateSelectionDialogState
    extends State<AvatarCandidateSelectionDialog> {
  String _selectedCandidateId = '';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF4F8),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(22),
                  border: Border.all(color: const Color(0xFFF0DCE5)),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(18, 22, 18, 18),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        '프로필에 지정할 아바타를 선택해주세요',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFF4A313B),
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        '선택한 아바타만 프로필에 표시돼요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF9A7785),
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        '원본 사진은 상대방에게 공개되지 않아요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF9A7785),
                        ),
                      ),
                      const SizedBox(height: 18),
                      GridView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              mainAxisSpacing: 10,
                              crossAxisSpacing: 10,
                            ),
                        itemCount: widget.candidates.length,
                        itemBuilder: (context, index) {
                          final candidate = widget.candidates[index];
                          final selected =
                              candidate.candidateId == _selectedCandidateId;
                          return Semantics(
                            label: '아바타 후보 ${index + 1}',
                            button: true,
                            selected: selected,
                            child: InkWell(
                              borderRadius: BorderRadius.circular(18),
                              onTap: widget.approving
                                  ? null
                                  : () => setState(() {
                                      _selectedCandidateId =
                                          candidate.candidateId;
                                    }),
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 160),
                                clipBehavior: Clip.antiAlias,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(18),
                                  border: Border.all(
                                    color: selected
                                        ? const Color(0xFFE48CB1)
                                        : const Color(0xFFF0DCE5),
                                    width: selected ? 3 : 1,
                                  ),
                                ),
                                child: Stack(
                                  fit: StackFit.expand,
                                  children: [
                                    _CandidateImage(candidate: candidate),
                                    if (selected)
                                      const Align(
                                        alignment: Alignment.topRight,
                                        child: Padding(
                                          padding: EdgeInsets.all(8),
                                          child: CircleAvatar(
                                            radius: 15,
                                            backgroundColor: Color(0xFFE48CB1),
                                            child: Icon(
                                              CupertinoIcons.check_mark,
                                              size: 18,
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 18),
                      SizedBox(
                        width: double.infinity,
                        height: 50,
                        child: ElevatedButton(
                          onPressed:
                              _selectedCandidateId.isEmpty || widget.approving
                              ? null
                              : () => widget.onApprove(_selectedCandidateId),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFFE48CB1),
                            foregroundColor: Colors.white,
                            disabledBackgroundColor: const Color(0xFFF0DCE5),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16),
                            ),
                          ),
                          child: Text(
                            widget.approving ? '저장하는 중...' : '이 사진으로 할게요!',
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _CandidateImage extends StatelessWidget {
  const _CandidateImage({required this.candidate});

  final AvatarCandidate candidate;

  @override
  Widget build(BuildContext context) {
    if (candidate.previewBytes != null) {
      return Image.memory(candidate.previewBytes!, fit: BoxFit.cover);
    }
    return Image.network(candidate.previewUrl, fit: BoxFit.cover);
  }
}
