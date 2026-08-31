/**
 * 3:3 블라인드 취향 미팅 — 앱 버전 호환 정책
 *
 * App Store와 TestFlight는 같은 Bundle ID/Firebase App ID를 공유하므로
 * App Check 앱 ID만으로 배포 채널을 구분할 수 없다. 기본 무료 테스트
 * 경로는 서버 환경변수에 명시한 UID allowlist를 사용한다.
 * UID를 미리 받을 수 없는 폐쇄 TestFlight 테스트를 위해, 만료시각과 최대
 * 계정 수가 함께 설정된 특정 앱 빌드에 한해 일회성 무료 슬롯을 허용할 수
 * 있다. 관련 환경변수가 없거나 하나라도 유효하지 않으면 유료 경로다.
 *
 * blindMeetingAction은 enforceAppCheck=true로 선언되어 있어 이 ID는
 * 임의의 클라이언트가 보내는 값이 아니라 검증된 App Check 요청의 사용자
 * 세션과 함께 처리된다.
 */

function parseUserIdAllowlist(raw: string | undefined): ReadonlySet<string> {
  return new Set(
    (raw ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter((value) => value.length > 0)
  );
}

/** 무료 블라인드 미팅 테스트를 명시적으로 허용한 사용자 UID 목록. */
export const FREE_BLIND_MEETING_TEST_USER_IDS: ReadonlySet<string> =
  parseUserIdAllowlist(process.env.BLIND_MEETING_FREE_TEST_UIDS);

export function isFreeBlindMeetingTestUser(
  userId: string,
  allowedUserIds: ReadonlySet<string> = FREE_BLIND_MEETING_TEST_USER_IDS
): boolean {
  return allowedUserIds.has(userId.trim());
}

export type FreeBlindMeetingTestBuildConfig = {
  build: string | null;
  builds: readonly string[];
  expiresAtMs: number | null;
  maxAccounts: number | null;
};

function parsePositiveInteger(raw: string | undefined): number | null {
  const parsed = Number.parseInt((raw ?? "").trim(), 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function parseBuildAllowlist(raw: string): readonly string[] {
  return [
    ...new Set(
      raw
        .split(",")
        .map((value) => value.trim())
        .filter((value) => value.length > 0)
    ),
  ];
}

/** 서버 환경변수에서 폐쇄 TestFlight 무료 빌드 정책을 읽는다. */
export function readFreeBlindMeetingTestBuildConfig(
  env: Record<string, string | undefined> = process.env
): FreeBlindMeetingTestBuildConfig {
  const rawExpiry = (env.BLIND_MEETING_FREE_TEST_EXPIRES_AT ?? "").trim();
  const parsedExpiry = rawExpiry.length > 0 ? Date.parse(rawExpiry) : Number.NaN;
  const rawBuild = (env.BLIND_MEETING_FREE_TEST_BUILD ?? "").trim();
  return {
    build: rawBuild.length > 0 ? rawBuild : null,
    builds: parseBuildAllowlist(rawBuild),
    expiresAtMs: Number.isFinite(parsedExpiry) ? parsedExpiry : null,
    maxAccounts: parsePositiveInteger(
      env.BLIND_MEETING_FREE_TEST_MAX_ACCOUNTS
    ),
  };
}

/**
 * 무료 TestFlight build gate.
 *
 * 이 값은 클라이언트가 보낸 build 번호만으로 신뢰하지 않는다. 호출 함수는
 * App Check를 강제하고, 아래 결과가 true일 때도 서버의 원자적 무료 슬롯
 * claim을 통과해야 무료 신청 경로를 사용한다.
 */
export function isFreeBlindMeetingTestBuild(
  clientBuild: unknown,
  nowMs = Date.now(),
  env: Record<string, string | undefined> = process.env
): boolean {
  const config = readFreeBlindMeetingTestBuildConfig(env);
  return (
    config.builds.length > 0 &&
    config.expiresAtMs != null &&
    config.maxAccounts != null &&
    config.expiresAtMs > nowMs &&
    config.builds.includes(String(clientBuild ?? "").trim())
  );
}

/**
 * 현재 무료 테스트 기간 안에 있는지 확인한다.
 *
 * 이전 TestFlight 앱은 clientBuild를 보내지 않는다. 이 호환 경로는
 * App Check가 통과한 기존 앱을 만료 시각까지만 허용하며, 실제 무료
 * 신청은 서버의 원자적 슬롯 claim을 한 번 더 통과해야 한다.
 */
export function isFreeBlindMeetingTestWindow(
  nowMs = Date.now(),
  env: Record<string, string | undefined> = process.env
): boolean {
  const config = readFreeBlindMeetingTestBuildConfig(env);
  return (
    config.builds.length > 0 &&
    config.expiresAtMs != null &&
    config.maxAccounts != null &&
    config.expiresAtMs > nowMs
  );
}

/** 현재 앱 빌드 또는 build 정보를 보내지 않는 기존 앱의 무료 테스트 판정. */
export function isFreeBlindMeetingTestClient(
  clientBuild: unknown,
  nowMs = Date.now(),
  env: Record<string, string | undefined> = process.env
): boolean {
  const normalizedBuild = String(clientBuild ?? "").trim();
  return normalizedBuild.length === 0
    ? isFreeBlindMeetingTestWindow(nowMs, env)
    : isFreeBlindMeetingTestBuild(normalizedBuild, nowMs, env);
}
