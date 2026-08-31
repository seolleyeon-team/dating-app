import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAvatarJobDoc,
  buildAvatarPayload,
} from "./avatarMedia";

test("avatar jobs use the canonical Azure GPT-Image-2 backend contract", () => {
  const payload = buildAvatarPayload(
    "u1",
    "src_1",
    "gs://private-source/users/u1/source/src_1.jpg",
    "job_1",
  );
  const job = buildAvatarJobDoc(payload);

  assert.equal(payload.modelId, "azure_gpt_image_2");
  assert.deepEqual(job.model, {
    provider: "azure",
    modelId: "azure_gpt_image_2",
    version: "gpt-image-2",
  });
  assert.equal(job.generationBackend, "azure_gpt_image_2");
  assert.deepEqual(job.provenance, {
    provider: "azure",
    generationBackend: "azure_gpt_image_2",
    modelFamily: "gpt-image-2",
    promptVersion: "avatar_general_prompt_v1",
    sourceInputMode: "storage_normalized_original_direct",
    uploadNormalization: "existing_avatar_media_ingestion",
    preGenerationTransform: "none",
    legacyTraitExtraction: false,
    legacyReferencePreprocessing: false,
    legacyFlux: false,
  });
});
