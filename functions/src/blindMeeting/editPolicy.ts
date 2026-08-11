import { MatchingStage, ParticipantStatus } from "./types";

export type BlindMeetingApplicationEditState = {
  status: ParticipantStatus;
  stage: MatchingStage;
  open: boolean;
  meetingId: string | null;
};

export type BlindMeetingApplicationEditPatch = {
  status: ParticipantStatus;
  stage: MatchingStage;
  open: true;
  meetingId: null;
  requestedDateKeys: string[];
  prefersAlcoholFree: boolean;
  waitlistOptIn: boolean;
};

/**
 * DNA may only be edited while the same application is still in the open
 * candidate pool. Matched/assigned applications are immutable from this flow.
 */
export function canEditBlindMeetingApplication(
  application: BlindMeetingApplicationEditState
): boolean {
  const editableStages: MatchingStage[] = [
    "searchingCandidates",
    "formingOwnTeam",
    "checkingCrossTeam",
    "awaitingConfirmation",
    "insufficientCandidates",
  ];
  return (
    application.open &&
    application.meetingId == null &&
    (application.status === "applied" || application.status === "waitlisted") &&
    editableStages.includes(application.stage)
  );
}

export function buildBlindMeetingApplicationEditPatch(
  application: BlindMeetingApplicationEditState,
  values: {
    requestedDateKeys: string[];
    prefersAlcoholFree: boolean;
    waitlistOptIn: boolean;
  }
): BlindMeetingApplicationEditPatch | null {
  if (!canEditBlindMeetingApplication(application)) return null;
  return {
    status: application.status,
    stage: "searchingCandidates",
    open: true,
    meetingId: null,
    requestedDateKeys: values.requestedDateKeys,
    prefersAlcoholFree: values.prefersAlcoholFree,
    waitlistOptIn: values.waitlistOptIn,
  };
}
