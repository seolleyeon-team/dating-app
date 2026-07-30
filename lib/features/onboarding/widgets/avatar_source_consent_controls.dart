import 'package:flutter/material.dart';

import '../models/avatar_source_consent.dart';

class AvatarSourceConsentControls extends StatelessWidget {
  const AvatarSourceConsentControls({
    super.key,
    required this.value,
    required this.locked,
    required this.onChanged,
  });

  static const Key clipRecommendationKey = Key(
    'avatar_source_clip_recommendation',
  );
  static const Key sourcePhotoRetentionKey = Key(
    'avatar_source_photo_retention',
  );

  final AvatarSourceConsent value;
  final bool locked;
  final ValueChanged<AvatarSourceConsent> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final titleStyle = theme.textTheme.bodyMedium?.copyWith(
      fontWeight: FontWeight.w700,
      color: const Color(0xFF181113),
    );
    final bodyStyle = theme.textTheme.bodySmall?.copyWith(
      color: const Color(0xFF89616F),
      height: 1.4,
    );

    return Semantics(
      container: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE6DBDF)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('아바타 생성 동의', style: titleStyle),
              const SizedBox(height: 6),
              Text(
                '업로드한 사진은 아바타 생성과 관련 안전 검토를 위해 처리됩니다. 이 항목은 아바타 생성에 필수입니다.',
                style: bodyStyle,
              ),
              const SizedBox(height: 10),
              CheckboxListTile(
                key: clipRecommendationKey,
                value: value.clipRecommendation,
                dense: true,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text('추천 품질 개선에 사용'),
                subtitle: const Text(
                  '선택하면 사진 처리 결과를 맞춤 추천 품질 개선에 함께 사용할 수 있습니다.',
                ),
                onChanged: locked
                    ? null
                    : (checked) => onChanged(
                        value.copyWith(clipRecommendation: checked == true),
                      ),
              ),
              CheckboxListTile(
                key: sourcePhotoRetentionKey,
                value: value.sourcePhotoRetention,
                dense: true,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text('원본 사진 보관 허용'),
                subtitle: const Text(
                  '선택하면 재생성, 오류 확인, 고객 문의 대응을 위해 원본 사진을 제한적으로 보관할 수 있습니다.',
                ),
                onChanged: locked
                    ? null
                    : (checked) => onChanged(
                        value.copyWith(sourcePhotoRetention: checked == true),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
