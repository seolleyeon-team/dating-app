/**
 * Pure helpers for season event-team invite acceptance.
 * Blind meeting is out of scope.
 */

export function canAcceptInviteIntoTeam(params: {
  acceptedUserIds: string[];
  inviteeUserId: string;
  capacity?: number;
}): { ok: true } | { ok: false; reason: "already_accepted" | "team_full" } {
  const capacity = params.capacity ?? 3;
  const accepted = [...new Set(params.acceptedUserIds.filter(Boolean))];
  if (accepted.includes(params.inviteeUserId)) {
    return { ok: false, reason: "already_accepted" };
  }
  if (accepted.length >= capacity) {
    return { ok: false, reason: "team_full" };
  }
  if (accepted.length + 1 > capacity) {
    return { ok: false, reason: "team_full" };
  }
  return { ok: true };
}

/** Simulates two concurrent accepts against the same snapshot (lost-update model). */
export function simulateConcurrentAcceptOverwrite(params: {
  acceptedUserIds: string[];
  inviteeA: string;
  inviteeB: string;
}): { withReplace: string[]; withArrayUnion: string[] } {
  const base = [...params.acceptedUserIds];
  const withReplaceA = [...base, params.inviteeA];
  const withReplaceB = [...base, params.inviteeB];
  // Last writer wins under naive replace — one member lost.
  const withReplace = withReplaceB;
  const withArrayUnion = [
    ...new Set([...base, params.inviteeA, params.inviteeB]),
  ];
  return { withReplace, withArrayUnion };
}
