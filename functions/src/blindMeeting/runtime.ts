/**
 * 3:3 블라인드 취향 미팅 — 함수 런타임 옵션
 * 경로: functions/src/blindMeeting/runtime.ts
 *
 * region을 함수마다 명시한다.
 * index.ts의 setGlobalOptions는 모듈 body에서 실행되지만 `export * from`는
 * import로 먼저 평가되므로, 전역 옵션에 의존하면 us-central1로 배포된다.
 *
 * 또한 프로젝트에 이미 많은 함수가 있어 region당 CPU 할당량이 빡빡하다.
 * 그래서 gen1 수준 CPU + 낮은 maxInstances를 사용하고,
 * 개별 callable을 하나의 dispatcher로 모아 함수 개수를 줄인다.
 */

export const BLIND_MEETING_REGION = "asia-northeast3";

export const BLIND_MEETING_CALLABLE_OPTIONS = {
  region: BLIND_MEETING_REGION,
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 5,
};

export const BLIND_MEETING_SCHEDULE_OPTIONS = {
  region: BLIND_MEETING_REGION,
  timeZone: "Asia/Seoul",
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 2,
  retryCount: 2,
};
