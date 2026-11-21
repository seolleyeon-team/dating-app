import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isPastDateKey } from "../types";

describe("isPastDateKey (KST)", () => {
  // 2026-11-13 00:30 KST == 2026-11-12 15:30 UTC
  const justAfterMidnightKst = Date.UTC(2026, 10, 12, 15, 30);

  it("어제는 지난 날짜다 (UTC 로는 아직 같은 날이어도)", () => {
    assert.equal(isPastDateKey("2026-11-12", justAfterMidnightKst), true);
    assert.equal(isPastDateKey("2026-10-31", justAfterMidnightKst), true);
  });

  it("오늘과 그 이후는 지난 날짜가 아니다", () => {
    assert.equal(isPastDateKey("2026-11-13", justAfterMidnightKst), false);
    assert.equal(isPastDateKey("2026-11-14", justAfterMidnightKst), false);
    assert.equal(isPastDateKey("2027-01-01", justAfterMidnightKst), false);
  });

  it("KST 자정 직전에는 그날이 아직 오늘이다", () => {
    // 2026-11-13 23:59 KST == 2026-11-13 14:59 UTC
    assert.equal(isPastDateKey("2026-11-13", Date.UTC(2026, 10, 13, 14, 59)), false);
    // 1분 뒤 KST 는 11-14 다.
    assert.equal(isPastDateKey("2026-11-13", Date.UTC(2026, 10, 13, 15, 0)), true);
  });
});
