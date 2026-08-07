# Phase 3 exact batch log

## Batch 002 freeze

Exactly ten tracked files are frozen for the first Phase 3 deletion batch. The batch contains five complete source/candidate pairs and no wildcard.

| Exact path | Bytes | SHA-256 | Backup | Reviewer A | Reviewer B |
|---|---:|---|---|---|---|
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_d0/source.png` | 1369 | `cc7bf2a4d59a6a0aad244660427728bbfe4244e78afe474781fc7c21fd7f6bf8` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_d0/candidate.png` | 1363 | `5ce279dc44feea60583afbe06f666e916fa1d1244ad2db108c7fb59a01435f67` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_d1/source.png` | 1369 | `cc7bf2a4d59a6a0aad244660427728bbfe4244e78afe474781fc7c21fd7f6bf8` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_d1/candidate.png` | 692 | `8c17f071097ab71579cbcd44f77bc266c40a964b29b77ed461b123180313f598` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_h0/source.png` | 1369 | `cc7bf2a4d59a6a0aad244660427728bbfe4244e78afe474781fc7c21fd7f6bf8` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_h0/candidate.png` | 107 | `131cafd494ec4060eeb45d47a8c701b14c4771ccf349c5b1afe67bf11610913e` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_k0/source.png` | 1369 | `cc7bf2a4d59a6a0aad244660427728bbfe4244e78afe474781fc7c21fd7f6bf8` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_k0/candidate.png` | 692 | `8c17f071097ab71579cbcd44f77bc266c40a964b29b77ed461b123180313f598` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_m0/source.png` | 1369 | `cc7bf2a4d59a6a0aad244660427728bbfe4244e78afe474781fc7c21fd7f6bf8` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_m0/candidate.png` | 1993 | `764e0c5caa5626a5dbbb9fc3c2468093ee1b8e5fa9d07d5654eef90ea4be901d` | verified | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |

Reviewer B independently verified the exact ten paths, 96×96 PNG headers, backup blob IDs, no consumers, and semantic regeneration evidence. Restore source is `backup/pre-dead-code-cleanup-20260804-060225`.

## Deferred after Batch 002

The remaining 25 tracked artifacts are not implicitly approved by this batch. They must be frozen in later exact batches of at most ten files, with the six legacy b/p PNGs and `ttl_report.json` explicitly classified.
