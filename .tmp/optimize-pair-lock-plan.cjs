const fs = require('fs');
const path = 'functions/src/teamMeetingRequest.ts';
const before = fs.readFileSync(path, 'utf8');
const oldText = '  return {\n    requestId: teamMeetingRequestId(sourceResultId, viewerGroupId, otherTeamId),\n    pairLockId: teamMeetingPairLockId(viewerGroupId, otherTeamId),\n    responseStatus: "pending",\n    requestData: {\n      pairLockId: teamMeetingPairLockId(viewerGroupId, otherTeamId),';
const newText = '  const pairLockId = teamMeetingPairLockId(viewerGroupId, otherTeamId);\n  return {\n    requestId: teamMeetingRequestId(sourceResultId, viewerGroupId, otherTeamId),\n    pairLockId,\n    responseStatus: "pending",\n    requestData: {\n      pairLockId,';
if (before.indexOf(oldText) < 0 || before.indexOf(oldText, before.indexOf(oldText) + 1) >= 0) {
  throw new Error('expected exactly one pair-lock return block');
}
fs.writeFileSync(path, before.replace(oldText, newText));
