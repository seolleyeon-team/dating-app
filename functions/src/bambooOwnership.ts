/**
 * P0-3 / SEC-04 — 대나무숲 소유권의 유일한 권위.
 *
 * public `bamboo_posts` / `comments` 문서는 로그인 사용자 누구나 읽는다. 그래서
 * 그 문서에는 작성자를 가리키는 값이 하나도 없어야 한다 (raw UID, 닉네임,
 * UID 해시 모두). 소유자는 서버와 본인만 읽을 수 있는 비공개 매핑에만 있다.
 *
 *   bamboo_post_authors/{postId}                       { postId, ownerUid }
 *   bamboo_comment_authors/{postId}__{commentId}       { postId, commentId, ownerUid }
 *   (Play 심사 파티션: playReviewBambooPostAuthors / playReviewBambooCommentAuthors)
 *
 * public `authorId` 로 되돌아가는 fallback 은 없다. 매핑이 없거나 깨졌으면
 * 소유자를 모르는 것이고, 그때는 아무에게도 알리지 않고 아무 권한도 주지 않는다
 * (fail closed). users / publicProfiles 를 뒤져 추측하지 않는다 — 그건 우리가
 * 없애려는 바로 그 join 이다.
 */

export const BAMBOO_POST_OWNER_COLLECTION = "bamboo_post_authors";
export const BAMBOO_COMMENT_OWNER_COLLECTION = "bamboo_comment_authors";
export const REVIEW_BAMBOO_POST_OWNER_COLLECTION = "playReviewBambooPostAuthors";
export const REVIEW_BAMBOO_COMMENT_OWNER_COLLECTION = "playReviewBambooCommentAuthors";

/**
 * public 대나무숲 문서에 다시는 들어가면 안 되는 필드. 서버 writer 테스트와
 * 마이그레이션 verify 가 같은 목록을 쓴다.
 */
export const BAMBOO_PUBLIC_IDENTITY_FIELDS = [
  "authorId",
  "authorUid",
  "ownerUid",
  "userId",
  "uid",
  "actorId",
  "actorName",
  "nickname",
  "authorName",
  "authorNickname",
  "authorProfileUrl",
  "profileId",
] as const;

/** 댓글은 글 하위라 commentId 만으로는 유일하지 않다. */
export function bambooCommentOwnerDocId(
  postId: string,
  commentId: string
): string {
  return `${postId}__${commentId}`;
}

export type BambooOwnerResolution =
  | { status: "mapped"; ownerUid: string }
  /** 매핑이 없다. 소유자를 모른다. */
  | { status: "missing" }
  /** 매핑은 있지만 ownerUid 가 비었거나 다른 글/댓글을 가리킨다. */
  | { status: "malformed" };

function clean(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * 매핑 문서 하나로 소유자를 정한다. `expected` 는 매핑 문서가 가리켜야 하는
 * postId / commentId 다 — 다른 글의 매핑이 잘못된 키에 놓인 경우를 걸러낸다.
 */
export function resolveBambooOwner(
  mapping: Record<string, unknown> | undefined | null,
  expected: { postId: string; commentId?: string }
): BambooOwnerResolution {
  if (mapping == null) return { status: "missing" };
  const ownerUid = clean(mapping.ownerUid);
  if (!ownerUid) return { status: "malformed" };
  if (clean(mapping.postId) && clean(mapping.postId) !== expected.postId) {
    return { status: "malformed" };
  }
  if (
    expected.commentId != null &&
    clean(mapping.commentId) &&
    clean(mapping.commentId) !== expected.commentId
  ) {
    return { status: "malformed" };
  }
  return { status: "mapped", ownerUid };
}

/** 소유자를 확신할 수 없으면 빈 문자열 — 호출부는 아무에게도 보내지 않는다. */
export function ownerUidOrEmpty(resolution: BambooOwnerResolution): string {
  return resolution.status === "mapped" ? resolution.ownerUid : "";
}

/** 대나무숲 알림에서 행위자를 나타내는 유일한 값. */
export const BAMBOO_ANONYMOUS_ACTOR_NAME = "익명";
