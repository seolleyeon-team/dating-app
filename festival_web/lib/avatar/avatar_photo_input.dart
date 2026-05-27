import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'avatar_generation_client.dart';

class AvatarPhotoInput extends StatelessWidget {
  const AvatarPhotoInput({
    super.key,
    required this.hasLocalPhoto,
    required this.sourceLocked,
    required this.approvedAvatarUrl,
    required this.isBusy,
    required this.fileName,
    required this.onPick,
    required this.onRemove,
    this.localPreviewBytes,
  });

  final bool hasLocalPhoto;
  final bool sourceLocked;
  final String approvedAvatarUrl;
  final bool isBusy;
  final String fileName;
  final VoidCallback onPick;
  final VoidCallback onRemove;
  final Uint8List? localPreviewBytes;

  bool get _approved => approvedAvatarUrl.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final canMutate = !sourceLocked && !_approved && !isBusy;
    return Material(
      color: Colors.transparent,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFFFFF8FB),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: hasLocalPhoto || _approved
                ? const Color(0xFFE48CB1)
                : const Color(0xFFF0DCE5),
          ),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: canMutate ? onPick : null,
          child: SizedBox(
            height: 178,
            width: double.infinity,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (_approved)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(21),
                    child: Image.network(approvedAvatarUrl, fit: BoxFit.cover),
                  )
                else if (localPreviewBytes != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(21),
                    child: Image.memory(localPreviewBytes!, fit: BoxFit.cover),
                  )
                else
                  const _EmptyAvatarPhotoInput(),
                if (hasLocalPhoto || _approved)
                  DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(21),
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.42),
                        ],
                      ),
                    ),
                  ),
                Positioned(
                  left: 16,
                  right: 16,
                  bottom: 14,
                  child: _AvatarPhotoInputStatus(
                    approved: _approved,
                    sourceLocked: sourceLocked,
                    isBusy: isBusy,
                    fileName: fileName,
                  ),
                ),
                if (canMutate && hasLocalPhoto) ...[
                  Positioned(
                    top: 12,
                    right: 12,
                    child: TextButton(
                      onPressed: onPick,
                      style: TextButton.styleFrom(
                        backgroundColor: Colors.black.withValues(alpha: 0.44),
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('다시 선택'),
                    ),
                  ),
                  Positioned(
                    top: 12,
                    left: 12,
                    child: Semantics(
                      label: '선택한 사진 제거',
                      button: true,
                      child: IconButton.filled(
                        onPressed: onRemove,
                        tooltip: '선택한 사진 제거',
                        icon: const Icon(CupertinoIcons.xmark),
                        style: IconButton.styleFrom(
                          backgroundColor: Colors.black.withValues(alpha: 0.44),
                          foregroundColor: Colors.white,
                        ),
                      ),
                    ),
                  ),
                ],
                if (isBusy)
                  const ColoredBox(
                    color: Color(0x55000000),
                    child: Center(
                      child: CircularProgressIndicator(color: Colors.white),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AvatarPhotoInputStatus extends StatelessWidget {
  const _AvatarPhotoInputStatus({
    required this.approved,
    required this.sourceLocked,
    required this.isBusy,
    required this.fileName,
  });

  final bool approved;
  final bool sourceLocked;
  final bool isBusy;
  final String fileName;

  @override
  Widget build(BuildContext context) {
    final title = approved
        ? '승인된 아바타'
        : sourceLocked
        ? avatarSourceLockedMessage
        : isBusy
        ? '아바타 생성 준비 중...'
        : '아바타로 만들 사진';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 15,
            height: 1.25,
            fontWeight: FontWeight.w900,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          approved ? '프로필에는 이 아바타만 표시돼요.' : fileName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.84),
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _EmptyAvatarPhotoInput extends StatelessWidget {
  const _EmptyAvatarPhotoInput();

  @override
  Widget build(BuildContext context) {
    return const Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(CupertinoIcons.photo, color: Color(0xFFE48CB1), size: 34),
        SizedBox(height: 10),
        Text(
          '사진 선택',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w800,
            color: Color(0xFF4A313B),
          ),
        ),
        SizedBox(height: 5),
        Text(
          '원본 사진은 상대방에게 공개되지 않아요.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: Color(0xFF9A7785),
          ),
        ),
      ],
    );
  }
}
