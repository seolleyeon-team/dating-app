import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import { assertSafeMemberText, normalizedUserText } from "./contentSafety";

type AppUser = { userId: string; data?: Record<string, unknown> };
type ResolveUser = (request: CallableRequest<unknown>) => Promise<AppUser>;

const CATEGORIES = new Set(["설렘", "고민", "일상", "질문"]);
const REVIEW_UID = "play-reviewer-v1";

function data(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function isReviewUser(user: AppUser): boolean {
  return user.userId === REVIEW_UID && user.data?.dataPartition === "play_review";
}

function roots(user: AppUser) {
  const review = isReviewUser(user);
  return {
    posts: review ? "playReviewBambooPosts" : "bamboo_posts",
    postOwners: review ? "playReviewBambooPostAuthors" : "bamboo_post_authors",
    commentOwners: review ? "playReviewBambooCommentAuthors" : "bamboo_comment_authors",
    review,
  };
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
      batch.set(postRef, {
        postId: postRef.id, authorId: user.userId, content, category, tags,
        createdAt: now, updatedAt: now, likeCount: 0, commentCount: 0,
        score7d: 0, isDeleted: false,
        ...(root.review ? { dataPartition: "play_review" } : {}),
      });
      batch.set(firestore.collection(root.postOwners).doc(postRef.id), {
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
      const post = await postRef.get();
      if (!post.exists || post.get("isDeleted") === true) {
        throw new HttpsError("not-found", "게시글을 찾을 수 없어요.");
      }
      if (parentCommentId) {
        const parent = await postRef.collection("comments").doc(parentCommentId).get();
        if (!parent.exists || parent.get("isDeleted") === true) {
          throw new HttpsError("not-found", "답글을 남길 댓글을 찾을 수 없어요.");
        }
      }
      const commentRef = postRef.collection("comments").doc();
      const now = FieldValue.serverTimestamp();
      const batch = firestore.batch();
      batch.set(commentRef, {
        commentId: commentRef.id, authorId: user.userId, content, parentCommentId,
        createdAt: now, updatedAt: now, likeCount: 0, isDeleted: false,
        ...(root.review ? { dataPartition: "play_review" } : {}),
      });
      batch.set(firestore.collection(root.commentOwners).doc(`${postId}__${commentRef.id}`), {
        postId, commentId: commentRef.id, ownerUid: user.userId, createdAt: now,
        ...(root.review ? { dataPartition: "play_review" } : {}),
      });
      batch.update(postRef, {
        commentCount: FieldValue.increment(1), score7d: FieldValue.increment(1), updatedAt: now,
      });
      await batch.commit();
      return { commentId: commentRef.id };
    }),
  };
}
