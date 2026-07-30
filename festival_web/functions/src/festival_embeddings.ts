import { onCall, onRequest, HttpsError } from "firebase-functions/v2/https";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import * as logger from "firebase-functions/logger";
import { FieldValue, getFirestore } from "firebase-admin/firestore";

const db = getFirestore();

const PROJECT_BUCKET =
  process.env.FIREBASE_STORAGE_BUCKET ||
  "seolleyeon-festival.firebasestorage.app";
const CLIP_MODEL_ID = "Xenova/clip-vit-base-patch32";

type ImageFeaturePipeline = (
  input: string,
  options?: { pooling?: string; normalize?: boolean }
) => Promise<{ data: Float32Array | number[] }>;

let pipelinePromise: Promise<ImageFeaturePipeline> | null = null;

async function getClipPipeline(): Promise<ImageFeaturePipeline> {
  if (!pipelinePromise) {
    pipelinePromise = (async () => {
      const { pipeline } = await import("@xenova/transformers");
      return pipeline("image-feature-extraction", CLIP_MODEL_ID) as Promise<ImageFeaturePipeline>;
    })();
  }
  return pipelinePromise;
}

function l2Normalize(vector: number[]): number[] {
  const norm = Math.sqrt(vector.reduce((sum, v) => sum + v * v, 0));
  if (norm <= 1e-12) return vector;
  return vector.map((v) => v / norm);
}

function tensorToVector(data: Float32Array | number[]): number[] {
  const raw = Array.from(data as ArrayLike<number>);
  return l2Normalize(raw.map((v) => Number(v)));
}

async function embedImageUrl(url: string): Promise<number[]> {
  const extractor = await getClipPipeline();
  const output = await extractor(url, { pooling: "mean", normalize: true });
  return tensorToVector(output.data);
}

function aiStorageUrl(code: string): string {
  const gender = code.startsWith("f") ? "female" : "male";
  const path = encodeURIComponent(`ai_profiles/${gender}/${code}.png`);
  return `https://firebasestorage.googleapis.com/v0/b/${PROJECT_BUCKET}/o/${path}?alt=media`;
}

async function writeAiEmbedding(code: string): Promise<void> {
  const imageUrl = aiStorageUrl(code);
  const vector = await embedImageUrl(imageUrl);
  await db.collection("festivalAiEmbeddings").doc(code).set(
    {
      code,
      vector,
      dims: vector.length,
      modelId: CLIP_MODEL_ID,
      imageUrl,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );
}

async function writeProfileEmbedding(
  ticketId: string,
  photoUrl: string
): Promise<void> {
  const vector = await embedImageUrl(photoUrl);
  await db.collection("festivalProfileEmbeddings").doc(ticketId).set(
    {
      ticketId,
      vector,
      dims: vector.length,
      modelId: CLIP_MODEL_ID,
      photoUrl,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );
}

export async function seedAllFestivalEmbeddings(): Promise<{
  aiCount: number;
  profileCount: number;
}> {
  const codes: string[] = [];
  for (let i = 1; i <= 20; i++) {
    codes.push(`f${i}`, `m${i}`);
  }

  let aiCount = 0;
  for (const code of codes) {
    try {
      await writeAiEmbedding(code);
      aiCount += 1;
      logger.info("AI embedding written", { code });
    } catch (error) {
      logger.warn("AI embedding failed", {
        code,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const profilesSnap = await db.collection("festivalProfiles").get();
  let profileCount = 0;
  for (const doc of profilesSnap.docs) {
    const photoUrl = String(doc.data().photoUrl ?? "").trim();
    if (!photoUrl) continue;
    try {
      await writeProfileEmbedding(doc.id, photoUrl);
      profileCount += 1;
      logger.info("Profile embedding written", { ticketId: doc.id });
    } catch (error) {
      logger.warn("Profile embedding failed", {
        ticketId: doc.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { aiCount, profileCount };
}

const SEED_HTTP_KEY = "seolleyeon-festival-clip-init";

/** HTTP bootstrap (no Firebase Auth) — use once via curl with x-seed-key header. */
export const seedFestivalEmbeddingsHttp = onRequest(
  {
    region: "asia-northeast3",
    memory: "2GiB",
    timeoutSeconds: 540,
    maxInstances: 1,
    invoker: "public",
  },
  async (req, res) => {
    if (req.get("x-seed-key") !== SEED_HTTP_KEY) {
      res.status(403).json({ error: "forbidden" });
      return;
    }
    try {
      logger.info("Festival embedding HTTP seed started");
      const result = await seedAllFestivalEmbeddings();
      const { generateRecommendationsForTicket } = await import(
        "./festival_recommendations.js"
      );
      const ticketsSnap = await db
        .collection("festivalTickets")
        .where("tasteCompleted", "==", true)
        .get();
      let recSuccess = 0;
      for (const doc of ticketsSnap.docs) {
        try {
          const rec = await generateRecommendationsForTicket(
            doc.id,
            "embedding_seed"
          );
          if (rec.success) recSuccess += 1;
        } catch (error) {
          logger.warn("Rec refresh after HTTP seed failed", {
            ticketId: doc.id,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
      res.json({ success: true, ...result, recommendationsRefreshed: recSuccess });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logger.error("Festival embedding HTTP seed failed", { error: message });
      res.status(500).json({ success: false, error: message });
    }
  }
);

/** One-time / maintenance: populate festivalAiEmbeddings + festivalProfileEmbeddings. */
export const seedFestivalEmbeddings = onCall(
  {
    region: "asia-northeast3",
    memory: "2GiB",
    timeoutSeconds: 540,
    maxInstances: 1,
  },
  async (request) => {
    if (!request.auth?.uid) {
      throw new HttpsError("unauthenticated", "로그인이 필요합니다.");
    }

    logger.info("Festival embedding seed started", { uid: request.auth.uid });
    const result = await seedAllFestivalEmbeddings();

    const { generateRecommendationsForTicket } = await import(
      "./festival_recommendations.js"
    );
    const ticketsSnap = await db
      .collection("festivalTickets")
      .where("tasteCompleted", "==", true)
      .get();
    let recSuccess = 0;
    for (const doc of ticketsSnap.docs) {
      try {
        const rec = await generateRecommendationsForTicket(
          doc.id,
          "embedding_seed"
        );
        if (rec.success) recSuccess += 1;
      } catch (error) {
        logger.warn("Rec refresh after seed failed", {
          ticketId: doc.id,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    logger.info("Festival embedding seed completed", {
      ...result,
      recommendationsRefreshed: recSuccess,
    });
    return { success: true, ...result, recommendationsRefreshed: recSuccess };
  }
);

/** Re-embed when a participant uploads or changes their profile photo. */
export const onFestivalProfilePhotoUpdated = onDocumentWritten(
  {
    document: "festivalProfiles/{ticketId}",
    region: "asia-northeast3",
    memory: "2GiB",
    timeoutSeconds: 120,
  },
  async (event) => {
    const after = event.data?.after;
    if (!after?.exists) return;

    const { areFestivalRecommendationsFrozen } = await import(
      "./festival_event_schedule"
    );
    if (await areFestivalRecommendationsFrozen()) return;

    const ticketId = event.params.ticketId;
    const photoUrl = String(after.data()?.photoUrl ?? "").trim();
    if (!photoUrl) return;

    const beforeUrl = event.data?.before?.exists
      ? String(event.data.before.data()?.photoUrl ?? "").trim()
      : "";
    if (beforeUrl === photoUrl && event.data?.before?.exists) return;

    try {
      await writeProfileEmbedding(ticketId, photoUrl);
      logger.info("Profile embedding updated on write", { ticketId });
    } catch (error) {
      logger.warn("Profile embedding update failed", {
        ticketId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
);
