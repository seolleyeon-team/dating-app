import assert from "node:assert/strict";
import test from "node:test";

import {
  avatarSourceRetentionLogFields,
  avatarSourceRetentionPrivacyFields,
} from "./avatarSourceRetention";

test("source retention privacy payloads hash job and photo identifiers without raw leaks", () => {
  const raw = {
    uid: "uid-secret",
    jobId: "job-secret",
    photoId: "photo-secret",
  };
  const logFields = avatarSourceRetentionLogFields(raw);
  const eventFields = avatarSourceRetentionPrivacyFields(raw);

  for (const fields of [logFields, eventFields]) {
    const serialized = JSON.stringify(fields);
    assert.equal(serialized.includes(raw.uid), false);
    assert.equal(serialized.includes(raw.jobId), false);
    assert.equal(serialized.includes(raw.photoId), false);
    assert.deepEqual(Object.keys(fields), ["uidHash", "jobIdHash", "photoIdHash"]);
    assert.equal(typeof fields.uidHash, "string");
    assert.equal(typeof fields.jobIdHash, "string");
    assert.equal(typeof fields.photoIdHash, "string");
  }
});