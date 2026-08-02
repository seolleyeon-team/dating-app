/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 함수 런타임 옵션
 * 경로: functions/src/meetingIcebreaker/runtime.ts
 *
 * blindMeeting/runtime.ts와 같은 이유로 region을 함수마다 명시한다.
 * `export * from`은 index.ts의 setGlobalOptions보다 먼저 평가되므로
 * 전역 옵션에 의존하면 us-central1로 배포된다.
 *
 * 프로젝트에 이미 함수가 많아 region당 CPU 할당량이 빡빡하므로
 * gen1 수준 CPU + 낮은 maxInstances를 사용한다.
 */

export const MEETING_ICEBREAKER_REGION = "asia-northeast3";

export const MEETING_ICEBREAKER_CALLABLE_OPTIONS = {
  region: MEETING_ICEBREAKER_REGION,
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 5,
};

export const MEETING_ICEBREAKER_SCHEDULE_OPTIONS = {
  region: MEETING_ICEBREAKER_REGION,
  timeZone: "Asia/Seoul",
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 2,
  retryCount: 2,
};

export const MEETING_ICEBREAKER_TASK_OPTIONS = {
  region: MEETING_ICEBREAKER_REGION,
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 5,
  retryConfig: {
    maxAttempts: 3,
    minBackoffSeconds: 30,
  },
  rateLimits: {
    maxConcurrentDispatches: 20,
  },
};

export const MEETING_ICEBREAKER_FIRESTORE_OPTIONS = {
  region: MEETING_ICEBREAKER_REGION,
  cpu: "gcf_gen1" as const,
  concurrency: 1,
  memory: "256MiB" as const,
  maxInstances: 5,
};
