/**
 * SEC-04 — 대나무숲 소유권 해석 (전환기).
 *
 * public `bamboo_posts` / `comments` 문서에는 아직 raw UID 가 `authorId` 로 들어
 * 있고 로그인만 하면 누구나 읽을 수 있다. 익명 글의 작성자를 특정할 수 있다는
 * 뜻이라 최종적으로는 그 필드를 없애야 한다. 그 사이 서버는 두 출처를 모두
 * 만나게 된다 — 이관된 문서는 비공개 매핑에, 아직 안 된 문서는 public
 * authorId 에만 소유자가 있다.
 *
 * 규칙은 단순하다. 매핑이 있으면 매핑이 정답이고, 없으면 legacy 를 임시로
 * 인정한다. 둘이 다르면 어느 쪽도 믿지 않는다 — 그 상태에서 한쪽을 고르면
 * 남의 글 알림을 엉뚱한 사람에게 보내게 된다.
 *
 * public authorId 제거가 끝나면 `legacy` 분기만 걷어내면 된다.
 */

export const BAMBOO_POST_OWNER_COLLECTION = "bamboo_post_authors";
export const BAMBOO_COMMENT_OWNER_COLLECTION = "bamboo_comment_authors";

/** 댓글은 글 하위라 commentId 만으로는 유일하지 않다. */
export function bambooCommentOwnerDocId(
  postId: string,
  commentId: string
): string {
  return `${postId}__${commentId}`;
}

export type BambooOwnerResolution =
  | { status: "mapped"; ownerUid: string }
  /** 아직 이관되지 않은 문서. public authorId 제거와 함께 사라진다. */
  | { status: "legacy"; ownerUid: string }
  | { status: "missing" }
  /** 매핑과 legacy 가 서로 다른 사람을 가리킨다. 알림을 보내지 않는다. */
  | { status: "conflict" };

function clean(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function resolveBambooOwner(
  mappedOwnerUid: unknown,
  legacyAuthorId: unknown
): BambooOwnerResolution {
  const mapped = clean(mappedOwnerUid);
  const legacy = clean(legacyAuthorId);

  if (mapped && legacy && mapped !== legacy) {
    return { status: "conflict" };
  }
  if (mapped) return { status: "mapped", ownerUid: mapped };
  if (legacy) return { status: "legacy", ownerUid: legacy };
  return { status: "missing" };
}

/**
 * 알림 대상으로 쓸 uid. 소유자를 확신할 수 없으면 빈 문자열을 돌려 호출부가
 * 아무에게도 보내지 않게 한다 — 여기서 users / publicProfiles 를 뒤져
 * 추측하지 않는다. 그건 우리가 없애려는 바로 그 join 이다.
 */
export function ownerUidForNotification(
  resolution: BambooOwnerResolution
): string {
  return resolution.status === "mapped" || resolution.status === "legacy"
    ? resolution.ownerUid
    : "";
}
