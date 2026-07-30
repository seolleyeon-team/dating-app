# PR8.5 blur diagnostics

Date: 2026-07-28

## Result

- Status: `PASS_LOCAL_DIAGNOSTIC`
- Participants: 10
- Previous accepted: 7
- Previous blur blocked: 3
- Live upload: 0
- Cloud mutation: none
- Production ready: false

S1, S2, and S4 are decision-relevant native/canonical face-quality stages. S0, S3, S5, S6, and S7 are diagnostic-only comparison stages.

## Anonymous blocked rows

| rowIndex | face size | exposure | contrast | compression | root cause | proposed decision |
| ---: | --- | --- | --- | --- | --- | --- |
| 4 | ge192 | normal | very_low | low | UNKNOWN_NEEDS_MORE_EVIDENCE | borderline |
| 5 | ge192 | normal | very_low | low | UNKNOWN_NEEDS_MORE_EVIDENCE | borderline |
| 9 | ge192 | normal | very_low | low | UNKNOWN_NEEDS_MORE_EVIDENCE | borderline |

Shadow decisions: {'borderline': 3, 'pass': 7}. The current ten-row cohort is diagnostic evidence only; borderline and review outcomes remain unresolved and thresholds are not production-calibrated.

The report contains only hashed participant labels and safe aggregate metrics. No live or deployment action was performed.
