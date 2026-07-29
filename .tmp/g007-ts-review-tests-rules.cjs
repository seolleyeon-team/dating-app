const fs = require('fs');

function replaceRequired(path, oldText, newText, label) {
  const content = fs.readFileSync(path, 'utf8');
  const first = content.indexOf(oldText);
  const second = content.indexOf(oldText, first + 1);
  if (first < 0 || second >= 0) throw new Error(`${label}: expected exactly one match`);
  fs.writeFileSync(path, content.replace(oldText, newText));
}

replaceRequired(
  'functions/src/chatRealPhoto.test.ts',
  '\n\ntest("valid chat participants with consent can use chat-profile photo asset"',
  `\n\ntest("approved avatar resolver rejects Festival private-media buckets", () => {\n  for (const url of [\n    "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",\n    "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png",\n    "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg?token=secret",\n  ]) {\n    assert.equal(\n      resolveSafeApprovedAvatarUrl({\n        avatar: { status: "approved", approvedAvatarUrl: url },\n      }),\n      "",\n      url\n    );\n  }\n});\n\ntest("valid chat participants with consent can use chat-profile photo asset"`,
  'chat Festival URL tests'
);

replaceRequired(
  'functions/src/avatarApproval.test.ts',
  '\n\ntest("different-candidate approval conflicts before copy when approval is in progress"',
  `\n\ntest("same-candidate approval rejects Festival private-media URLs", () => {\n  for (const approvedAvatarUrl of [\n    "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",\n    "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png",\n    "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg?token=secret",\n  ]) {\n    const plan = planAvatarApprovalState(\n      {\n        avatar: {\n          status: "approved",\n          selectedCandidateId: "cand_1",\n          approvedAvatarUrl,\n          avatarId: "avatar_1",\n        },\n      },\n      "cand_1"\n    );\n\n    assert.equal(plan.action, "reserve", approvedAvatarUrl);\n  }\n});\n\ntest("different-candidate approval conflicts before copy when approval is in progress"`,
  'approval Festival URL tests'
);

replaceRequired(
  'functions/src/teamMeetingRequest.test.ts',
  '  teamMeetingMatchId,\n  teamMeetingRequestId,',
  '  teamMeetingMatchId,\n  teamMeetingPairLockId,\n  teamMeetingRequestId,',
  'pair lock import'
);
replaceRequired(
  'functions/src/teamMeetingRequest.test.ts',
  '  assert.equal(plan.requestId, teamMeetingRequestId("result-1", "team-a", "team-b"));\n  assert.equal(plan.responseStatus, "pending");',
  '  assert.equal(plan.requestId, teamMeetingRequestId("result-1", "team-a", "team-b"));\n  assert.equal(plan.pairLockId, teamMeetingPairLockId("team-a", "team-b"));\n  assert.equal(plan.requestData.pairLockId, plan.pairLockId);\n  assert.equal(plan.responseStatus, "pending");',
  'pair lock plan assertions'
);
replaceRequired(
  'functions/src/teamMeetingRequest.test.ts',
  '\n\ntest("create request plan rejects callers outside the selected team"',
  `\n\ntest("different results for the same team pair share one pending-request lock", () => {\n  const first = buildCreateTeamMeetingRequestPlan({\n    sourceResultId: "result-1",\n    viewerGroupId: "team-a",\n    callerUid: "a1",\n    matchResultData: matchResult,\n  });\n  const second = buildCreateTeamMeetingRequestPlan({\n    sourceResultId: "result-2",\n    viewerGroupId: "team-b",\n    callerUid: "b1",\n    matchResultData: { ...matchResult, resultId: "result-2" },\n  });\n\n  assert.notEqual(first.requestId, second.requestId);\n  assert.equal(first.pairLockId, second.pairLockId);\n});\n\ntest("create request plan rejects callers outside the selected team"`,
  'same pair different result test'
);

replaceRequired(
  'firestore.rules',
  `    match /eventTeamMeetingRequests/{requestId} {\n      allow read: if isEventTeamMatchParticipant(resource.data);\n      allow write: if false;\n    }\n`,
  `    match /eventTeamMeetingRequests/{requestId} {\n      allow read: if isEventTeamMatchParticipant(resource.data);\n      allow write: if false;\n    }\n\n    match /eventTeamMeetingRequestLocks/{lockId} {\n      allow read, write: if false;\n    }\n`,
  'pair lock rules'
);

replaceRequired(
  'functions/src/firestoreRules.test.ts',
  `  assertContains(\n    "three-vs-three matches must be participant-readable and backend-written",`,
  `  assertContains(\n    "team meeting pair locks must deny every client operation",\n    "match /eventTeamMeetingRequestLocks/{lockId} { allow read, write: if false; }"\n  );\n  assertContains(\n    "three-vs-three matches must be participant-readable and backend-written",`,
  'pair lock rules test'
);
replaceRequired(
  'functions/src/firestoreRules.test.ts',
  '  assert.match(service, /httpsCallable\\(\'respondTeamMeetingRequest\'\\)/);\n',
  '  assert.match(service, /httpsCallable\\(\'respondTeamMeetingRequest\'\\)/);\n  assert.match(service, /await _requireFirebaseReadSession\\(\\)/);\n',
  'read session static test'
);
