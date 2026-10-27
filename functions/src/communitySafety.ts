import { createHash } from "node:crypto";
import { FieldValue, type Firestore, type Transaction } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import {
  BAMBOO_COMMENT_OWNER_COLLECTION,
  BAMBOO_POST_OWNER_COLLECTION,
  REVIEW_BAMBOO_COMMENT_OWNER_COLLECTION,
  REVIEW_BAMBOO_POST_OWNER_COLLECTION,
  bambooCommentOwnerDocId,
  resolveBambooOwner,
} from "./bambooOwnership";
import { assertSafeMemberText, normalizedUserText } from "./contentSafety";

/**
 * 대나무숲 (익명 게시판) 의 모든 소유권 관련 쓰기.
 *
 * P0-3: public 글/댓글 문서에는 작성자를 가리키는 값이 없다. 소유자는 같은
 * 커밋에서 쓰는 비공개 매핑에만 있고, 삭제·신고처럼 소유자를 알아야 하는
 * 동작은 전부 이 서버 경로에서 매핑으로 판정한다. 클라이언트는 소유자 UID 를
 * 보내지도, 받지도 않는다.
 */

type AppUser = { userId: string; data?: Record<string, unknown> };
type ResolveUser = (request: CallableRequest<unknown>) => Promise<AppUser>;

const CATEGORIES = new Set(["설렘", "고민", "일상", "질문"]);
const REVIEW_UID = "play-reviewer-v1";
const REPORT_REASONS = new Set(["괴롭힘·혐오", "성적 콘텐츠", "스팸·광고", "개인정보 노출", "기타"]);
export const BAMBOO_HIDDEN_CONTENT_SUBCOLLECTION = "bambooHiddenContent";

function data(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function isReviewUser(user: AppUser): boolean {
  return user.userId === REVIEW_UID && user.data?.dataPartition === "play_review";
}

export function bambooRoots(review: boolean) {
  return {
    posts: review ? "playReviewBambooPosts" : "bamboo_posts",
    postOwners: review ? REVIEW_BAMBOO_POST_OWNER_COLLECTION : BAMBOO_POST_OWNER_COLLECTION,
    commentOwners: review ? REVIEW_BAMBOO_COMMENT_OWNER_COLLECTION : BAMBOO_COMMENT_OWNER_COLLECTION,
    review,
  };
}

function roots(user: AppUser) {
  return bambooRoots(isReviewUser(user));
}

function tagList(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 10) {
    throw new HttpsError("invalid-argument", "tags must contain at most 10 items.");
  }
  return [...new Set(value.map((item) => normalizedUserText(item, "tag", 30)))];
}

function id(value: unknown, field: string): string {
  const result = typeof value === "string" ? value.trim() : "";
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(result)) {
    throw new HttpsError("invalid-argument", `${field} is invalid.`);
  }
  return result;
}

/**
 * 소유자가 아니면 — 매핑이 없거나, 깨졌거나, 남의 것이면 — 모두 같은 오류를
 * 낸다. 경우마다 다른 응답을 주면 "이 글에 매핑이 있는가 / 누구 것인가" 를
 * 시험하는 오라클이 된다.
 */
const NOT_OWNER = () => new HttpsError("permission-denied", "작성자만 삭제할 수 있어요.");

async function requireOwnership(
  tx: Transaction,
  firestore: Firestore,
  collection: string,
  docId: string,
  expected: { postId: string; commentId?: string },
  callerUid: string
): Promise<void> {
  const mapping = await tx.get(firestore.collection(collection).doc(docId));
  const resolution = resolveBambooOwner(mapping.exists ? mapping.data() : null, expected);
  if (resolution.status !== "mapped" || resolution.ownerUid !== callerUid) throw NOT_OWNER();
}

export function bambooHiddenContentKey(postId: string, commentId: string | null): string {
  return commentId ? `${postId}__${commentId}` : postId;
}

export function createCommunitySafetyCallables(firestore: Firestore, resolveUser: ResolveUser) {
  return {
    createCommunityPost: onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
      const user = await resolveUser(request);
      const input = data(request.data);
      const content = assertSafeMemberText(input.content, "content", 500);
      const category = normalizedUserText(input.category, "category", 40);
      if (!CATEGORIES.has(category)) {
        throw new HttpsError("invalid-argument", "category is invalid.");
      }
      const tags = tagList(input.tags ?? []);
      const root = roots(user);
      const postRef = firestore.collection(root.posts).doc();
      const now = FieldValue.serverTimestamp();
      const batch = firestore.batch();
      // public 문서와 비공개 매핑은 한 커밋이다 — 매핑 없는 글은 생기지 않는다.
      batch.create(postRef, {
        postId: postRef.id, content, category, tags,
        createdAt: now, updatedAt: now, likeCount: 0, commentCount: 0,
        score7d: 0, isDeleted: false,
        ...(root.review ? { dataPartition: "play_review" } : {}),
      });
      batch.create(firestore.collection(root.postOwners).doc(postRef.id), {
        postId: postRef.id, ownerUid: user.userId, createdAt: now,
        ...(root.review ? { dataPartition: "play_review" } : {}),
      });
      await batch.commit();
      return { postId: postRef.id };
    }),

    createCommunityComment: onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
      const user = await resolveUser(request);
      const input = data(request.data);
      const postId = id(input.postId, "postId");
      const content = assertSafeMemberText(input.content, "content", 500);
      const parentCommentId = input.parentCommentId == null ? null : id(input.parentCommentId, "parentCommentId");
      const root = roots(user);
      const postRef = firestore.collection(root.posts).doc(postId);
      const commentRef = postRef.collection("comments").doc();
      await firestore.runTransaction(async (tx) => {
        const post = await tx.get(postRef);
        if (!post.exists || post.get("isDeleted") === true) {
          throw new HttpsError("not-found", "게시글을 찾을 수 없어요.");
        }
        if (parentCommentId) {
          const parent = await tx.get(postRef.collection("comments").doc(parentCommentId));
          if (!parent.exists || parent.get("isDeleted") === true) {
            throw new HttpsError("not-found", "답글을 남길 댓글을 찾을 수 없어요.");
          }
        }
        const now = FieldValue.serverTimestamp();
        tx.create(commentRef, {
          commentId: commentRef.id, content, parentCommentId,
          createdAt: now, updatedAt: now, likeCount: 0, isDeleted: false,
          ...(root.review ? { dataPartition: "play_review" } : {}),
        });
        tx.create(firestore.collection(root.commentOwners).doc(bambooCommentOwnerDocId(postId, commentRef.id)), {
          postId, commentId: commentRef.id, ownerUid: user.userId, createdAt: now,
          ...(root.review ? { dataPartition: "play_review" } : {}),
        });
        tx.update(postRef, {
          commentCount: FieldValue.increment(1), score7d: FieldValue.increment(1), updatedAt: now,
        });
      });
      return { commentId: commentRef.id };
    }),

    /** 본인 글 삭제 (soft delete). 소유 판정은 비공개 매핑으로만 한다. */
    deleteCommunityPost: onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
      const user = await resolveUser(request);
      const postId = id(data(request.data).postId, "postId");
      const root = roots(user);
      const postRef = firestore.collection(root.posts).doc(postId);
      await firestore.runTransaction(async (tx) => {
        const post = await tx.get(postRef);
        if (!post.exists) throw new HttpsError("not-found", "게시글을 찾을 수 없어요.");
        await requireOwnership(tx, firestore, root.postOwners, postId, { postId }, user.userId);
        if (post.get("isDeleted") === true) return;
        tx.update(postRef, { isDeleted: true, updatedAt: FieldValue.serverTimestamp() });
      });
      return { ok: true };
    }),

    /** 본인 댓글/답글 삭제 (soft delete) + 글의 commentCount 정정. */
    deleteCommunityComment: onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
      const user = await resolveUser(request);
      const input = data(request.data);
      const postId = id(input.postId, "postId");
      const commentId = id(input.commentId, "commentId");
      const root = roots(user);
      const postRef = firestore.collection(root.posts).doc(postId);
      const commentRef = postRef.collection("comments").doc(commentId);
      await firestore.runTransaction(async (tx) => {
        const [post, comment] = await Promise.all([tx.get(postRef), tx.get(commentRef)]);
        if (!post.exists || !comment.exists) throw new HttpsError("not-found", "댓글을 찾을 수 없어요.");
        await requireOwnership(
          tx, firestore, root.commentOwners, bambooCommentOwnerDocId(postId, commentId),
          { postId, commentId }, user.userId
        );
        if (comment.get("isDeleted") === true) return;
        const now = FieldValue.serverTimestamp();
        tx.update(commentRef, { isDeleted: true, updatedAt: now });
        const count = Number(post.get("commentCount") ?? 0);
        tx.update(postRef, {
          commentCount: Number.isFinite(count) && count > 0 ? FieldValue.increment(-1) : 0,
          updatedAt: now,
        });
      });
      return { ok: true };
    }),

    /**
     * 대나무숲 글/댓글 신고. 작성자는 서버가 매핑으로 찾아 운영 신고 문서에만
     * 남긴다 (reports 는 클라이언트가 읽을 수 없다). 신고한 사람에게는 그
     * 콘텐츠를 숨김 목록에 넣어 줄 뿐, 작성자 UID 나 "같은 작성자의 다른 글"
     * 같은 연결 정보는 돌려주지 않는다.
     *
     * 실명 기반 차단(blocks/{me}/targets/{uid}) 은 만들지 않는다. 그 문서는
     * 신고자가 읽을 수 있어 익명 작성자의 UID 를 그대로 알려 주고, 반대 방향
     * 문서는 작성자에게 신고자를 알려 준다.
     */
    reportBambooContent: onCall({ enforceAppCheck: true, timeoutSeconds: 30, memory: "256MiB" }, async (request) => {
      const user = await resolveUser(request);
      const input = data(request.data);
      const contentType = input.contentType;
      if (contentType !== "bamboo_post" && contentType !== "bamboo_comment") {
        throw new HttpsError("invalid-argument", "contentType is invalid.");
      }
      const postId = id(input.postId, "postId");
      const commentId = contentType === "bamboo_comment" ? id(input.commentId, "commentId") : null;
      const reason = typeof input.reason === "string" ? input.reason.trim() : "";
      if (!REPORT_REASONS.has(reason)) throw new HttpsError("invalid-argument", "reason is invalid.");
      const details = input.details == null ? null : normalizedUserText(input.details, "details", 2000);
      const root = roots(user);
      const partition = root.review ? "play_review" : "production";
      const contentRef = commentId
        ? firestore.collection(root.posts).doc(postId).collection("comments").doc(commentId)
        : firestore.collection(root.posts).doc(postId);
      const ownerRef = commentId
        ? firestore.collection(root.commentOwners).doc(bambooCommentOwnerDocId(postId, commentId))
        : firestore.collection(root.postOwners).doc(postId);
      const key = bambooHiddenContentKey(postId, commentId);
      const reportId = "bamboo_" + createHash("sha256")
        .update(`${user.userId}|${contentType}|${key}`).digest("hex").slice(0, 40);
      const reportRef = firestore.collection("reports").doc(reportId);
      const hiddenRef = firestore.collection("users").doc(user.userId)
        .collection(BAMBOO_HIDDEN_CONTENT_SUBCOLLECTION).doc(key);

      await firestore.runTransaction(async (tx) => {
        const [content, owner, existing] = await Promise.all([tx.get(contentRef), tx.get(ownerRef), tx.get(reportRef)]);
        if (!content.exists) throw new HttpsError("not-found", "신고할 콘텐츠를 찾을 수 없어요.");
        const resolution = resolveBambooOwner(owner.exists ? owner.data() : null, { postId, commentId: commentId ?? undefined });
        const ownerUid = resolution.status === "mapped" ? resolution.ownerUid : null;
        if (ownerUid === user.userId) {
          throw new HttpsError("failed-precondition", "내가 쓴 글은 신고할 수 없어요.");
        }
        const now = FieldValue.serverTimestamp();
        if (!existing.exists) {
          tx.create(reportRef, {
            reporterId: user.userId,
            // 작성자를 모르면 null 로 남기고 운영이 콘텐츠 경로로 조사한다.
            reportedId: ownerUid,
            ownershipStatus: resolution.status,
            reason,
            details,
            source: contentType,
            contentType,
            contentId: commentId ?? postId,
            parentContentId: commentId ? postId : null,
            status: root.review ? "test_only" : "pending",
            dataPartition: partition,
            reviewFixture: root.review,
            createdAt: now,
          });
        }
        tx.set(hiddenRef, {
          contentType,
          postId,
          commentId,
          dataPartition: partition,
          createdAt: now,
        }, { merge: true });
      });
      return { ok: true, hidden: true };
    }),
  };
}
