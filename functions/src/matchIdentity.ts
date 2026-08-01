export class InvalidMatchUserIdsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidMatchUserIdsError";
  }
}

function normalizeUserId(value: string): string {
  return typeof value === "string" ? value.trim() : "";
}

export function sortUserPair(userA: string, userB: string): [string, string] {
  const a = normalizeUserId(userA);
  const b = normalizeUserId(userB);
  if (!a || !b) {
    throw new InvalidMatchUserIdsError("user ids must be non-empty");
  }
  return [a, b].sort() as [string, string];
}

export function buildDirectRoomId(userA: string, userB: string): string {
  const [first, second] = sortUserPair(userA, userB);
  return `dm_${first}_${second}`;
}

export function buildDeterministicMatchId(
  userA: string,
  userB: string
): string {
  const [first, second] = sortUserPair(userA, userB);
  return `match_${first}_${second}`;
}
