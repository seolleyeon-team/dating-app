import '../../../data/models/event/event_team_match_model.dart';
import '../../../data/models/event/team_meeting_request_model.dart';

class TeamFriendPickerArgs {
  final String teamSetupId;

  const TeamFriendPickerArgs({required this.teamSetupId});
}

class EventTeamInviteResponseArgs {
  final String inviteId;

  const EventTeamInviteResponseArgs({required this.inviteId});
}

class SeasonMeetingRouletteArgs {
  final String teamSetupId;

  const SeasonMeetingRouletteArgs({required this.teamSetupId});
}

/// match_result_screen.dart 진입 모드
enum MatchResultEntryMode {
  /// 슬롯 머신 결과 화면에서 진입 (기존 동작)
  slotResult,

  /// 팀 요청 리스트의 받은 요청에서 진입
  receivedTeamRequest,

  /// 팀 요청 리스트의 보낸 요청에서 진입
  sentTeamRequest,
}

class EventMatchResultArgs {
  final String resultId;
  final EventTeamMatchResult? initialResult;
  final String? viewerGroupId;

  /// 진입 모드 (기본: 슬롯 결과)
  final MatchResultEntryMode entryMode;

  /// 팀 요청 리스트에서 진입 시 request 정보
  final String? requestId;
  final TeamMeetingRequestDoc? requestDoc;

  const EventMatchResultArgs({
    required this.resultId,
    this.initialResult,
    this.viewerGroupId,
    this.entryMode = MatchResultEntryMode.slotResult,
    this.requestId,
    this.requestDoc,
  });
}

/// three_vs_three_match_screen.dart 진입 인자
class ThreeVsThreeMatchArgs {
  final String matchId;

  const ThreeVsThreeMatchArgs({required this.matchId});
}

/// 요청 거절 화면 진입 인자
class TeamRequestDeclinedArgs {
  final String requestId;
  final EventTeamMatchTeamSnapshot? otherTeamSnapshot;

  const TeamRequestDeclinedArgs({
    required this.requestId,
    this.otherTeamSnapshot,
  });
}
