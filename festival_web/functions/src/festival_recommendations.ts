import { onSchedule } from "firebase-functions/v2/scheduler";
import {
  onDocumentCreated,
  onDocumentUpdated,
} from "firebase-functions/v2/firestore";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { FieldValue, getFirestore } from "firebase-admin/firestore";

const db = getFirestore();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

function asNumber(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const parsed = Number(v);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function kstDateKey(now = new Date()): string {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

// ---------------------------------------------------------------------------
// Embedding utilities (used when festivalAiEmbeddings / festivalProfileEmbeddings exist)
// ---------------------------------------------------------------------------

function l2Normalize(vector: number[]): number[] {
  const norm = Math.sqrt(vector.reduce((sum, v) => sum + v * v, 0));
  if (norm <= 1e-12) return vector;
  return vector.map((v) => v / norm);
}

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length === 0 || a.length !== b.length) return 0;
  let dot = 0;
  let nA = 0;
  let nB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    nA += a[i] * a[i];
    nB += b[i] * b[i];
  }
  if (nA <= 1e-12 || nB <= 1e-12) return 0;
  return dot / (Math.sqrt(nA) * Math.sqrt(nB));
}

function weightedMean(
  samples: Array<{ vector: number[]; weight: number }>
): number[] | null {
  if (samples.length === 0) return null;
  const dims = samples[0].vector.length;
  const acc = Array(dims).fill(0);
  let wSum = 0;
  for (const s of samples) {
    if (s.vector.length !== dims || s.weight <= 0) continue;
    wSum += s.weight;
    for (let i = 0; i < dims; i++) acc[i] += s.vector[i] * s.weight;
  }
  if (wSum <= 1e-12) return null;
  return l2Normalize(acc.map((v) => v / wSum));
}

async function loadVector(
  collection: string,
  docId: string
): Promise<number[] | null> {
  const snap = await db.collection(collection).doc(docId).get();
  if (!snap.exists) return null;
  const raw = snap.data()?.vector;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  return raw.map((v) => asNumber(v));
}

// ---------------------------------------------------------------------------
// Preference vector from taste swipes + AI embeddings (if available)
// ---------------------------------------------------------------------------

const LIKE_WEIGHT = 1.0;
const DISLIKE_WEIGHT = 0.65;

async function buildPreferenceVector(
  ticketId: string
): Promise<number[] | null> {
  const ticketSnap = await db.collection("festivalTickets").doc(ticketId).get();
  const ticketData = ticketSnap.data() ?? {};
  const stored = ticketData.preferenceVector as
    | Record<string, unknown>
    | undefined;
  const storedVector = Array.isArray(stored?.vector)
    ? (stored?.vector as unknown[]).map((v) => asNumber(v))
    : null;
  if (storedVector && storedVector.length > 0) return storedVector;

  const swipesSnap = await db
    .collection("festivalTickets")
    .doc(ticketId)
    .collection("tasteSwipes")
    .get();

  const positive: Array<{ vector: number[]; weight: number }> = [];
  const negative: Array<{ vector: number[]; weight: number }> = [];
  const affinities: Record<string, number> = {};

  for (const doc of swipesSnap.docs) {
    const data = doc.data();
    const code = asString(data.aiProfileCode);
    if (!code) continue;
    affinities[code] = data.liked === true ? 1 : 0;
    const embedding = await loadVector("festivalAiEmbeddings", code);
    if (!embedding) continue;
    if (data.liked === true)
      positive.push({ vector: embedding, weight: LIKE_WEIGHT });
    else negative.push({ vector: embedding, weight: DISLIKE_WEIGHT });
  }

  const posMean = weightedMean(positive);
  const negMean = weightedMean(negative);
  let preference: number[] | null = null;
  if (posMean && negMean) {
    preference = l2Normalize(
      posMean.map((v, i) => v - DISLIKE_WEIGHT * (negMean[i] ?? 0))
    );
  } else if (posMean) {
    preference = posMean;
  }

  if (Object.keys(affinities).length > 0 || preference) {
    await db
      .collection("festivalTickets")
      .doc(ticketId)
      .set(
        {
          aiProfileAffinities: affinities,
          ...(preference
            ? {
                preferenceVector: {
                  vector: preference,
                  dims: preference.length,
                  modelId: "festival-clip-v1",
                  confidence: Math.min(1, positive.length / 6),
                  source: "festival_taste_swipes",
                  computedAt: FieldValue.serverTimestamp(),
                },
              }
            : {}),
          aiProfileAffinityUpdatedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
  }

  if (preference) return preference;
  return loadVector("festivalProfileEmbeddings", ticketId);
}

// ---------------------------------------------------------------------------
// MVP profile-based scoring (works WITHOUT embeddings)
// ---------------------------------------------------------------------------

const MBTI_COMPAT: Record<string, string[]> = {
  INFP: ["ENFJ", "ENTJ"],
  ENFP: ["INFJ", "INTJ"],
  INFJ: ["ENFP", "ENTP"],
  ENFJ: ["INFP", "ISFP"],
  INTJ: ["ENFP", "ENTP"],
  ENTJ: ["INFP", "INTP"],
  INTP: ["ENTJ", "ESTJ"],
  ENTP: ["INFJ", "INTJ"],
  ISFP: ["ENFJ", "ESFJ", "ESTJ"],
  ESFP: ["ISFJ", "ISTJ"],
  ISTP: ["ESFJ", "ESTJ"],
  ESTP: ["ISFJ", "ISTJ"],
  ISFJ: ["ESFP", "ESTP"],
  ESFJ: ["ISFP", "ISTP"],
  ISTJ: ["ESFP", "ESTP"],
  ESTJ: ["INTP", "ISTP", "ISFP"],
};

/** Freed from removed heuristics (dept / selectivity / hash); applied to face/embedding base. */
const FACE_BASE_WEIGHT = 0.15;

interface ProfileData {
  ticketId: string;
  gender: string;
  age: number;
  mbti: string;
  department: string;
  photoUrl: string;
  nickname: string;
  intro: string;
  studentAffiliation: string;
}

function readProfileData(
  docId: string,
  data: Record<string, unknown>
): ProfileData {
  return {
    ticketId: docId,
    gender: asString(data.gender),
    age: asNumber(data.age, 20),
    mbti: asString(data.mbti).toUpperCase().trim(),
    department: asString(data.department),
    photoUrl: asString(data.photoUrl),
    nickname: asString(data.nickname, "익명"),
    intro: asString(data.intro),
    studentAffiliation: asString(data.studentAffiliation),
  };
}

function profileScore(user: ProfileData, candidate: ProfileData): number {
  // MVP fallback base (0.50 + freed 0.15 from removed heuristics)
  let score = 0.5 + FACE_BASE_WEIGHT;

  // MBTI compatibility (0 - 0.20)
  if (user.mbti && candidate.mbti) {
    const bestMatches = MBTI_COMPAT[user.mbti] ?? [];
    if (bestMatches.includes(candidate.mbti)) {
      score += 0.20;
    } else if (user.mbti[0] !== candidate.mbti[0]) {
      // I/E complementary
      score += 0.08;
    } else if (user.mbti.slice(1) === candidate.mbti.slice(1)) {
      score += 0.05;
    }
  }

  // Age proximity (0 - 0.15)
  const ageDiff = Math.abs(user.age - candidate.age);
  if (ageDiff <= 1) score += 0.15;
  else if (ageDiff <= 2) score += 0.12;
  else if (ageDiff <= 3) score += 0.08;
  else if (ageDiff <= 5) score += 0.04;

  return Math.min(1.0, Math.max(0, score));
}

/** Embedding cosine with base weight so face signal dominates ranking. */
function embeddingScore(preference: number[], candidate: number[]): number {
  const cosine = Math.max(0, cosineSimilarity(preference, candidate));
  return FACE_BASE_WEIGHT + (1 - FACE_BASE_WEIGHT) * cosine;
}

// ---------------------------------------------------------------------------
// Core recommendation generator
// ---------------------------------------------------------------------------

const MAX_RECOMMENDATIONS = 3;

interface RecommendationItem {
  ticketId: string;
  rank: number;
  score: number;
  matchPercent: number;
  nickname: string;
  photoUrl: string;
  age: number;
  department: string;
  mbti: string;
  intro: string;
  studentAffiliation: string;
  scoringMethod: string;
}

interface GenerationResult {
  success: boolean;
  recommendations: RecommendationItem[];
  insufficientSlots: number;
  totalCandidates: number;
  scoringMethod: string;
  error?: string;
}

export async function generateRecommendationsForTicket(
  ticketId: string,
  generatedBy: string
): Promise<GenerationResult> {
  // 1. Load current user's profile
  const profileSnap = await db
    .collection("festivalProfiles")
    .doc(ticketId)
    .get();
  if (!profileSnap.exists) {
    return {
      success: false,
      recommendations: [],
      insufficientSlots: MAX_RECOMMENDATIONS,
      totalCandidates: 0,
      scoringMethod: "none",
      error: "프로필이 등록되지 않았습니다.",
    };
  }
  const userProfile = readProfileData(ticketId, profileSnap.data() ?? {});
  if (!userProfile.gender) {
    return {
      success: false,
      recommendations: [],
      insufficientSlots: MAX_RECOMMENDATIONS,
      totalCandidates: 0,
      scoringMethod: "none",
      error: "성별 정보가 없습니다.",
    };
  }

  const targetGender = userProfile.gender === "남성" ? "여성" : "남성";

  // 2. Try building embedding-based preference vector
  const preferenceVector = await buildPreferenceVector(ticketId);
  const hasEmbeddings = preferenceVector !== null;

  // 4. Load opposite-gender candidate profiles
  const candidatesSnap = await db
    .collection("festivalProfiles")
    .where("gender", "==", targetGender)
    .get();

  // 5. Load exclusion sets
  const [disabledSnap, reportsSnap] = await Promise.all([
    db
      .collection("festivalTicketEnforcement")
      .where("disabled", "==", true)
      .get(),
    db
      .collection("festivalDeveloperReports")
      .where("reporterTicketId", "==", ticketId)
      .where("status", "==", "open")
      .get(),
  ]);

  const disabledTickets = new Set(disabledSnap.docs.map((d) => d.id));
  const reportedTickets = new Set(
    reportsSnap.docs.map((d) => asString(d.data().reportedTicketId))
  );
  const excludeSet = new Set([...disabledTickets, ...reportedTickets, ticketId]);

  // 6. Score candidates
  const scored: Array<{
    profile: ProfileData;
    score: number;
    method: string;
  }> = [];

  for (const doc of candidatesSnap.docs) {
    if (excludeSet.has(doc.id)) continue;
    const candidate = readProfileData(doc.id, doc.data());

    let score: number;
    let method: string;

    if (hasEmbeddings) {
      const candidateEmbedding = await loadVector(
        "festivalProfileEmbeddings",
        doc.id
      );
      if (candidateEmbedding) {
        score = embeddingScore(preferenceVector, candidateEmbedding);
        method = "embedding";
      } else {
        score = profileScore(userProfile, candidate);
        method = "profile_mvp";
      }
    } else {
      score = profileScore(userProfile, candidate);
      method = "profile_mvp";
    }

    scored.push({ profile: candidate, score, method });
  }

  scored.sort((a, b) => b.score - a.score);
  const topN = scored.slice(0, MAX_RECOMMENDATIONS);
  const scoringMethod = hasEmbeddings ? "embedding+profile_mvp" : "profile_mvp";

  const recommendations: RecommendationItem[] = topN.map((entry, index) => ({
    ticketId: entry.profile.ticketId,
    rank: index + 1,
    score: entry.score,
    matchPercent: Math.round(
      Math.min(97, Math.max(72, 72 + (entry.score + 1) * 13))
    ),
    nickname: entry.profile.nickname,
    photoUrl: entry.profile.photoUrl,
    age: entry.profile.age,
    department: entry.profile.department,
    mbti: entry.profile.mbti,
    intro: entry.profile.intro,
    studentAffiliation: entry.profile.studentAffiliation,
    scoringMethod: entry.method,
  }));

  const insufficientSlots = Math.max(0, MAX_RECOMMENDATIONS - recommendations.length);
  const totalCandidates = candidatesSnap.docs.filter(
    (d) => !excludeSet.has(d.id)
  ).length;

  // 7. Save to festivalRecommendations/{ticketId}
  const dateKey = kstDateKey();
  const recDoc = {
    ticketId,
    userGender: userProfile.gender,
    targetGender,
    updatedAt: FieldValue.serverTimestamp(),
    generatedAt: FieldValue.serverTimestamp(),
    generatedBy,
    dateKey,
    roundId: 1,
    scoringMethod,
    totalCandidates,
    insufficientSlots,
    recommendedProfileIds: recommendations.map((r) => r.ticketId),
    scores: recommendations.map((r) => r.score),
    recommendations,
  };

  await db
    .collection("festivalRecommendations")
    .doc(ticketId)
    .set(recDoc, { merge: false });

  // 8. Also write to legacy festivalModelRecs for backward compatibility
  const legacyItems = recommendations.map((r) => ({
    ticketId: r.ticketId,
    uid: r.ticketId,
    rank: r.rank,
    score: r.score,
  }));

  if (legacyItems.length > 0) {
    await db
      .collection("festivalModelRecs")
      .doc(ticketId)
      .collection("daily")
      .doc(dateKey)
      .collection("sources")
      .doc("clip")
      .set(
        {
          status: "ready",
          algorithmVersion: `festival_${scoringMethod}_v1`,
          model: { type: "clip", source: "festival_functions" },
          generatedAt: FieldValue.serverTimestamp(),
          topN: legacyItems.length,
          items: legacyItems,
        },
        { merge: true }
      );
  }

  logger.info("Festival recommendations generated", {
    ticketId,
    generatedBy,
    scoringMethod,
    count: recommendations.length,
    insufficientSlots,
    totalCandidates,
  });

  return {
    success: true,
    recommendations,
    insufficientSlots,
    totalCandidates,
    scoringMethod,
  };
}

// ---------------------------------------------------------------------------
// Callable function — invoked by "추천 새로고침" button
// ---------------------------------------------------------------------------

export const refreshFestivalRecommendations = onCall(
  {
    region: "asia-northeast3",
    maxInstances: 10,
    timeoutSeconds: 120,
  },
  async (request) => {
    const uid = request.auth?.uid;
    if (!uid) {
      throw new HttpsError("unauthenticated", "로그인이 필요합니다.");
    }

    const sessionSnap = await db.collection("festivalSessions").doc(uid).get();
    if (!sessionSnap.exists) {
      throw new HttpsError("not-found", "세션이 없습니다. 다시 로그인해주세요.");
    }
    const ticketId = asString(sessionSnap.data()?.ticketId);
    if (!ticketId) {
      throw new HttpsError(
        "failed-precondition",
        "입장 코드가 확인되지 않습니다."
      );
    }

    const enforcementSnap = await db
      .collection("festivalTicketEnforcement")
      .doc(ticketId)
      .get();
    if (enforcementSnap.exists && enforcementSnap.data()?.disabled === true) {
      throw new HttpsError(
        "permission-denied",
        "비활성화된 계정입니다."
      );
    }

    const result = await generateRecommendationsForTicket(
      ticketId,
      "debug_refresh"
    );

    if (!result.success) {
      throw new HttpsError(
        "failed-precondition",
        result.error ?? "추천 생성에 실패했습니다."
      );
    }

    return {
      success: true,
      count: result.recommendations.length,
      insufficientSlots: result.insufficientSlots,
      totalCandidates: result.totalCandidates,
      scoringMethod: result.scoringMethod,
    };
  }
);

// ---------------------------------------------------------------------------
// Firestore triggers (kept for backward compatibility + auto-generation)
// ---------------------------------------------------------------------------

export const onFestivalTasteCompleted = onDocumentUpdated(
  "festivalTickets/{ticketId}",
  async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();
    if (!before || !after) return;
    if (before.tasteCompleted === true || after.tasteCompleted !== true) return;

    const { isFestivalEventScheduleActive } = await import(
      "./festival_event_schedule"
    );
    if (await isFestivalEventScheduleActive()) return;

    const ticketId = event.params.ticketId;
    const result = await generateRecommendationsForTicket(
      ticketId,
      "taste_completed"
    );
    logger.info("Festival taste-completed recommendation", {
      ticketId,
      success: result.success,
      count: result.recommendations.length,
    });
  }
);

export const onFestivalRecommendationJobCreated = onDocumentCreated(
  "festivalRecommendationJobs/{jobId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const jobRef = snap.ref;
    const data = snap.data();
    const ticketId = asString(data.ticketId);
    const requestedByUid = asString(data.requestedByUid);

    try {
      if (!ticketId || !requestedByUid) {
        throw new Error("ticketId/requestedByUid is required");
      }

      const sessionSnap = await db
        .collection("festivalSessions")
        .doc(requestedByUid)
        .get();
      if (
        !sessionSnap.exists ||
        sessionSnap.data()?.ticketId !== ticketId
      ) {
        throw new Error("requester does not own the active ticket session");
      }

      await jobRef.set(
        {
          status: "running",
          startedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );

      const result = await generateRecommendationsForTicket(
        ticketId,
        "debug_refresh"
      );

      if (!result.success) {
        throw new Error(result.error ?? "recommendation generation failed");
      }

      const dateKey = kstDateKey();
      await jobRef.set(
        {
          status: "ready",
          dateKey,
          modelRecPath: `festivalModelRecs/${ticketId}/daily/${dateKey}/sources/clip`,
          recPath: `festivalRecommendations/${ticketId}`,
          completedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );

      logger.info("Festival debug recommendation job completed", {
        jobId: event.params.jobId,
        ticketId,
        dateKey,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await jobRef.set(
        {
          status: "failed",
          errorMessage: message,
          completedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      logger.warn("Festival debug recommendation job failed", {
        jobId: event.params.jobId,
        ticketId,
        error: message,
      });
    }
  }
);

export const generateFestivalDailyRecommendations = onSchedule(
  {
    schedule: "0 17 * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
  },
  async () => {
    const ticketsSnap = await db
      .collection("festivalTickets")
      .where("tasteCompleted", "==", true)
      .get();

    let success = 0;
    for (const doc of ticketsSnap.docs) {
      try {
        const result = await generateRecommendationsForTicket(
          doc.id,
          "scheduled_batch"
        );
        if (result.success) success += 1;
      } catch (error) {
        logger.warn("Festival scheduled rec generation failed", {
          ticketId: doc.id,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    logger.info("Festival daily recommendations completed", {
      total: ticketsSnap.size,
      success,
    });
  }
);
