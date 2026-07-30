// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 게임 목록
// 경로: lib/features/event/meeting_icebreaker/domain/meeting_icebreaker_game.dart
//
// 룰렛 8칸의 순서와 이름은 이 파일이 유일한 출처다.
// 화면에서 문자열을 다시 적지 않는다.
//
// 설명(description)은 현재 테스트용 번호(1~8)만 담고 있다.
// 실제 게임 규칙이 확정되면 이 파일의 description만 교체하면 된다.
// =============================================================================

/// 룰렛 칸 종류. 순서가 곧 룰렛의 1번~8번 칸 순서다.
enum MeetingRouletteGameType {
  /// 1. 귓속말게임
  whisper,

  /// 2. 랭킹게임
  ranking,

  /// 3. 이미지게임
  image,

  /// 4. 폭탄 돌리기 (당첨 시 타이머 게임으로 이동 가능)
  bombPass,

  /// 5. 출석부
  attendance,

  /// 6. 다음 게임 동안 벌주 *2잔 (비음주 미팅에서는 문구 대체)
  doubleDrinkPenalty,

  /// 7. 침묵의 공공칠빵
  silent007,

  /// 8. 두부 게임
  tofu,
}

/// 룰렛 칸 수. 8칸 고정이다 (문구를 대체해도 칸 수는 유지한다).
const int kMeetingRouletteSegmentCount = 8;

/// 자율 참여 안내. 룰렛 팝업과 결과 창에 함께 노출한다.
const String kMeetingRouletteParticipationNotice =
    '모든 게임은 자율 참여예요. 불편한 게임은 건너뛰어도 괜찮아요.';

/// 음주 관련 안내. 음주 칸이 있을 때만 노출한다.
const String kMeetingRouletteAlcoholNotice =
    '음주는 선택이에요. 무알코올 음료나 다른 벌칙으로 바꿔도 괜찮아요.';

/// 룰렛 한 칸.
class MeetingRouletteGame {
  const MeetingRouletteGame({
    required this.type,
    required this.number,
    required this.title,
    required this.description,
    this.opensBombTimer = false,
    this.mentionsAlcohol = false,
  });

  final MeetingRouletteGameType type;

  /// 룰렛에서의 순번 (1~8). 현재는 설명 창에 그대로 보여준다.
  final int number;

  /// 사용자에게 보여주는 게임 이름.
  final String title;

  /// 결과 설명. 지금은 테스트 목적으로 번호 문자열만 담는다.
  final String description;

  /// 결과 창에 `타이머 열기` CTA를 노출할지. 폭탄 돌리기만 true.
  final bool opensBombTimer;

  /// 음주 안내를 함께 보여줘야 하는 칸인지.
  final bool mentionsAlcohol;

  /// 룰렛 칸 index (0-based).
  int get index => number - 1;

  @override
  String toString() => 'MeetingRouletteGame(${type.name}, $number)';
}

/// 음주 표현을 쓸 수 없을 때 6번 칸을 대체하는 문구.
const String kMeetingRouletteNonAlcoholPenaltyTitle = '다음 게임 동안 벌칙 2회';

/// 6번 칸의 기본(음주) 문구.
const String kMeetingRouletteAlcoholPenaltyTitle = '다음 게임 동안 벌주 *2잔';

/// 룰렛 8칸을 순서대로 만든다.
///
/// [alcoholFreeCopy]가 true면 음주 벌칙 칸을 비음주 문구로 대체한다.
/// 무알코올 미팅이거나 서비스 정책상 음주 표현이 허용되지 않는 경우에 쓴다.
/// 칸 수(8)와 순서는 바뀌지 않는다.
List<MeetingRouletteGame> buildMeetingRouletteGames({
  bool alcoholFreeCopy = false,
}) {
  return <MeetingRouletteGame>[
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.whisper,
      number: 1,
      title: '귓속말게임',
      description: '1',
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.ranking,
      number: 2,
      title: '랭킹게임',
      description: '2',
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.image,
      number: 3,
      title: '이미지게임',
      description: '3',
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.bombPass,
      number: 4,
      title: '폭탄 돌리기',
      description: '4',
      opensBombTimer: true,
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.attendance,
      number: 5,
      title: '출석부',
      description: '5',
    ),
    MeetingRouletteGame(
      type: MeetingRouletteGameType.doubleDrinkPenalty,
      number: 6,
      title: alcoholFreeCopy
          ? kMeetingRouletteNonAlcoholPenaltyTitle
          : kMeetingRouletteAlcoholPenaltyTitle,
      description: '6',
      mentionsAlcohol: !alcoholFreeCopy,
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.silent007,
      number: 7,
      title: '침묵의 공공칠빵',
      description: '7',
    ),
    const MeetingRouletteGame(
      type: MeetingRouletteGameType.tofu,
      number: 8,
      title: '두부 게임',
      description: '8',
    ),
  ];
}

/// 짧은 라벨 (룰렛 칸 안에 들어가는 텍스트).
///
/// 칸이 좁아 두 줄로 끊어 넣을 때 사용한다.
List<String> meetingRouletteSegmentLabelLines(MeetingRouletteGame game) {
  switch (game.type) {
    case MeetingRouletteGameType.whisper:
      return const <String>['귓속말', '게임'];
    case MeetingRouletteGameType.ranking:
      return const <String>['랭킹', '게임'];
    case MeetingRouletteGameType.image:
      return const <String>['이미지', '게임'];
    case MeetingRouletteGameType.bombPass:
      return const <String>['폭탄', '돌리기'];
    case MeetingRouletteGameType.attendance:
      return const <String>['출석부'];
    case MeetingRouletteGameType.doubleDrinkPenalty:
      return game.mentionsAlcohol
          ? const <String>['벌주', '2잔']
          : const <String>['벌칙', '2회'];
    case MeetingRouletteGameType.silent007:
      return const <String>['침묵의', '공공칠빵'];
    case MeetingRouletteGameType.tofu:
      return const <String>['두부', '게임'];
  }
}
