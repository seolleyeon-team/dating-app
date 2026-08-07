# Phase 2 exact-file review matrix

Audit date: 2026-08-04. This matrix freezes Batch 001 before any deletion.

## Batch 001 frozen scope

Exactly 10 tracked files are in this batch. No directory wildcard and no image/report path is included.

| Exact path | Size | SHA-256 | Backup ref | Classification | Reviewer A | Reviewer B |
|---|---:|---|---|---|---|---|
| `pytest_tmp_avatar_qa_escalated/test_avatar_ttl_cleanup_scriptcurrent` | 108 | `19b8ba4a47107ec195cd48656a3536de6339f4f459a7c02580430563b3893c7c` | `backup/pre-dead-code-cleanup-20260804-060225` | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_bcurrent` | 108 | `2fe7d73ea27dec98ccdec24376465d4b18a8cad432ca0640b326d60a1791a30a` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_dcurrent` | 108 | `0c938c7bb91cf1fabda8c6964771cca7a01465376d58def1103758973261728e` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_hcurrent` | 108 | `2dcd08094d22dc6ef3a6b80424f185ffa7ca6a77e8f7c27d7b607e6597003846` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_kcurrent` | 108 | `1a89bbae1820903d38303e801b44daf6aac3fe3e7bba81545ea5efa64d161395` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_mcurrent` | 108 | `a2c639355b7e994ff55f54b24fd168927aeaa5fa19b65423a90b7fd95797d16e` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_pcurrent` | 108 | `c6481978d07363ad84cb71a6195fda960bacc60e7f0d6ab48a58a9b527a5e190` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_rcurrent` | 108 | `b1e07eb3359a3b41ad90eb7538a947d84dd92bb26e82f617011a4ac6556b7b2e` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_scurrent` | 108 | `ae1a5815eed35abfa57d108c3028c0e76696e7ea790bf60577fa6f3fa4fb5230` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |
| `pytest_tmp_avatar_qa_escalated/test_run_avatar_candidate_qa_ucurrent` | 108 | `ec03de5a785df7256846ee77922952dc13983da5644d7888328bad9fe8a06bad` | same | pytest current pointer | APPROVE_SAFE_TO_REMOVE | APPROVE_SAFE_TO_REMOVE |

## Evidence shared by all ten paths

- Each file is a 108-byte text pointer containing a local absolute path under the same pytest artifact directory. It is not Dart, Python, TypeScript, JSON configuration, a route, an asset, or a Firebase payload.
- The only exact directory references outside the candidate scope are analyzer/editor exclusion entries at `analysis_options.yaml:36` and `.vscode/settings.json:22`; these remain valid if the directory is absent.
- `tests/test_avatar_qa_cleanup.py:129` writes generated PNGs under pytest `tmp_path`; the QA tests at lines 288-611 and the TTL report test at lines 893-950 consume temporary paths, not checked-in pointers.
- No exact path reference was found in runtime source, route/deep-link strings, background handlers, DI/provider registration, Functions/Tasks/Scheduler exports, native/web registration, assets, CI, or workflow documents.
- Git history shows all 45 candidate paths were added together by `c4fe98dd` (`avatar canary backup`). All ten paths exist in `backup/pre-dead-code-cleanup-20260804-060225`.
- A reproducible equivalent command is `.venv\\Scripts\\python.exe -m pytest tests\\test_avatar_qa_cleanup.py -q --basetemp pytest_tmp_avatar_qa_escalated`; exact byte-for-byte output is not required for these disposable pointers.

## Twelve-check result

| Check | Result for all ten pointers | Evidence / reason |
|---|---|---|
| 1. Static imports/exports | PASS: zero | Plain pytest pointer text; no code symbol |
| 2. String/dynamic refs | PASS: zero exact consumers | Bounded `rg`/`git grep`; only directory excludes |
| 3. Routes/deep links | PASS: none | Not a route or URL payload |
| 4. Entry/background | PASS: none | Not an entry point; no pragma/callback |
| 5. DI/provider | PASS: none | Not executable code |
| 6. Firebase/Tasks/Scheduler | PASS: none | Not configuration or payload |
| 7. Native/web | PASS: none | Not registered by a platform file |
| 8. Assets/resources | PASS: none | Pointer is not an image/audio/resource consumed by app |
| 9. Tests/CI/fixtures | PASS: disposable output | Test code creates its own `tmp_path`; pointer is not imported fixture |
| 10. Workflow/runtime protection | PASS: not protected | No workflow/runtime feature relation |
| 11. Git/WIP/ownership/restore | PASS | Added in c4fe98dd; backup contains all; current WIP branch was not changed |
| 12. Reviewer A+B | PASS | Primary review and independent Reviewer B both approved exact paths |

## Deferred exact paths

The remaining 35 files under this directory are not in Batch 001: 34 generated `candidate.png`/`source.png` files and one `ttl_report.json`. Reviewer B considers them likely disposable test outputs, but they remain deferred because the repository does not document the exact byte-for-byte basetemp invocation. They require a later exact batch and fresh pre/post evidence.

Batch 001 is therefore limited to the ten pointer files above.
