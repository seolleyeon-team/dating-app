// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 당첨 게임 설명 창
// 경로: lib/features/event/meeting_icebreaker/presentation/meeting_game_result_sheet.dart
//
// 현재는 게임 이름과 테스트용 번호(1~8)만 보여준다.
// 폭탄 돌리기만 `타이머 열기` CTA를 추가로 노출한다.
// 게임 종류 판정은 문자열 비교가 아니라 enum(MeetingRouletteGameType)으로 한다.
// =============================================================================

import 'package:flutter/material.dart';

import '../domain/meeting_icebreaker_game.dart';
import 'meeting_icebreaker_keys.dart';
import 'meeting_icebreaker_palette.dart';

/// 설명 창에서 사용자가 고른 다음 행동.
enum MeetingGameResultAction {
  /// 전체 팝업 종료.
  close,

  /// 룰렛으로 돌아가 다시 돌리기.
  spinAgain,

  /// 폭탄 돌리기 타이머 열기.
  openBombTimer,
}

Future<MeetingGameResultAction?> showMeetingGameResultSheet({
  required BuildContext context,
  required MeetingRouletteGame game,
  required MeetingIcebreakerPalette palette,
  bool bombPassEnabled = true,
}) {
  return showModalBottomSheet<MeetingGameResultAction>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (sheetContext) => MeetingGameResultSheet(
      game: game,
      palette: palette,
      bombPassEnabled: bombPassEnabled,
    ),
  );
}

class MeetingGameResultSheet extends StatelessWidget {
  const MeetingGameResultSheet({
    super.key,
    required this.game,
    required this.palette,
    this.bombPassEnabled = true,
  });

  final MeetingRouletteGame game;
  final MeetingIcebreakerPalette palette;
  final bool bombPassEnabled;

  bool get _showBombTimerCta => game.opensBombTimer && bombPassEnabled;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;

    return Container(
      key: MeetingIcebreakerKeys.resultSheet,
      decoration: BoxDecoration(
        color: palette.surface,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(kMeetingIcebreakerDialogRadius),
        ),
        border: Border.all(color: palette.border),
      ),
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 12,
        bottom: 20 + bottomInset,
      ),
      child: SafeArea(
        top: false,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Center(
                child: Container(
                  width: 44,
                  height: 4,
                  decoration: BoxDecoration(
                    color: palette.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Semantics(
                liveRegion: true,
                label: '당첨된 게임은 ${game.title}, 설명 번호 ${game.description}',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      game.title,
                      key: MeetingIcebreakerKeys.resultTitle,
                      textAlign: TextAlign.center,
                      style: MeetingIcebreakerText.resultTitle(palette.ink),
                    ),
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 18),
                      decoration: BoxDecoration(
                        color: palette.surfaceMuted,
                        borderRadius: BorderRadius.circular(
                          kMeetingIcebreakerCardRadius,
                        ),
                      ),
                      child: Text(
                        game.description,
                        key: MeetingIcebreakerKeys.resultNumber,
                        textAlign: TextAlign.center,
                        style: MeetingIcebreakerText.resultNumber(
                          palette.accentDeep,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              if (game.mentionsAlcohol)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _NoticeBox(
                    key: MeetingIcebreakerKeys.alcoholNotice,
                    text: kMeetingRouletteAlcoholNotice,
                    palette: palette,
                    tone: _NoticeTone.attention,
                  ),
                ),
              _NoticeBox(
                text: kMeetingRouletteParticipationNotice,
                palette: palette,
                tone: _NoticeTone.neutral,
              ),
              const SizedBox(height: 20),
              if (_showBombTimerCta)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _PrimaryButton(
                    key: MeetingIcebreakerKeys.resultBombTimerButton,
                    label: '타이머 열기',
                    palette: palette,
                    onPressed: () => Navigator.of(
                      context,
                    ).pop(MeetingGameResultAction.openBombTimer),
                  ),
                ),
              Row(
                children: <Widget>[
                  Expanded(
                    child: _SecondaryButton(
                      key: MeetingIcebreakerKeys.resultSpinAgainButton,
                      label: '다시 돌리기',
                      palette: palette,
                      onPressed: () => Navigator.of(
                        context,
                      ).pop(MeetingGameResultAction.spinAgain),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _SecondaryButton(
                      key: MeetingIcebreakerKeys.resultCloseButton,
                      label: '닫기',
                      palette: palette,
                      onPressed: () => Navigator.of(
                        context,
                      ).pop(MeetingGameResultAction.close),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

enum _NoticeTone { neutral, attention }

class _NoticeBox extends StatelessWidget {
  const _NoticeBox({
    super.key,
    required this.text,
    required this.palette,
    required this.tone,
  });

  final String text;
  final MeetingIcebreakerPalette palette;
  final _NoticeTone tone;

  @override
  Widget build(BuildContext context) {
    final isAttention = tone == _NoticeTone.attention;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: isAttention ? palette.surfaceMuted : palette.sage,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        text,
        style: MeetingIcebreakerText.caption(
          isAttention ? palette.accentDeep : palette.inkSoft,
        ),
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    super.key,
    required this.label,
    required this.palette,
    required this.onPressed,
  });

  final String label;
  final MeetingIcebreakerPalette palette;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: kMeetingIcebreakerCtaHeight,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: palette.accent,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(kMeetingIcebreakerCardRadius),
          ),
        ),
        child: FittedBox(
          child: Text(label, style: MeetingIcebreakerText.cta(Colors.white)),
        ),
      ),
    );
  }
}

class _SecondaryButton extends StatelessWidget {
  const _SecondaryButton({
    super.key,
    required this.label,
    required this.palette,
    required this.onPressed,
  });

  final String label;
  final MeetingIcebreakerPalette palette;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 48,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: palette.ink,
          side: BorderSide(color: palette.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
        child: FittedBox(
          child: Text(label, style: MeetingIcebreakerText.body(palette.ink)),
        ),
      ),
    );
  }
}
