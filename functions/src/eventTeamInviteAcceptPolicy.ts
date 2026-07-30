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

/**
 * Builds the post-accept membership list for a Firestore transaction.
 * Prefer writing this exact array (with OCC) over arrayUnion so capacity is
 * an explicit postcondition of the same write.
 */
export function nextAcceptedUserIds(params: {
  acceptedUserIds: string[];
  inviteeUserId: string;
  capacity?: number;
}):
  | { ok: true; acceptedUserIds: string[]; memberCount: number }
  | { ok: false; reason: "already_accepted" | "team_full" } {
  const gate = canAcceptInviteIntoTeam(params);
  if (!gate.ok) return gate;
  const acceptedUserIds = [
    ...new Set([...params.acceptedUserIds.filter(Boolean), params.inviteeUserId]),
  ];
  const capacity = params.capacity ?? 3;
  if (acceptedUserIds.length > capacity) {
    return { ok: false, reason: "team_full" };
  }
  return {
    ok: true,
    acceptedUserIds,
    memberCount: acceptedUserIds.length,
  };
}

/** Simulates two concurrent accepts against the same snapshot (lost-update model). */
export function simulateConcurrentAcceptOverwrite(params: {
  acceptedUserIds: string[];
  inviteeA: string;
  inviteeB: string;
}): { withReplace: string[]; withArrayUnion: string[] } {
  const base = [...params.acceptedUserIds];
  // Last writer wins under naive replace — one member lost.
  const withReplace = [...base, params.inviteeB];
  const withArrayUnion = [
    ...new Set([...base, params.inviteeA, params.inviteeB]),
  ];
  return { withReplace, withArrayUnion };
}
