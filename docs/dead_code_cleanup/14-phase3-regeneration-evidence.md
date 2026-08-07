# Phase 3 regeneration evidence

Audit date: 2026-08-04. This document records the read-only generator proof used before Batch 002.

## Reproduction command

The test was executed from cleanup worktree `chore/dead-code-cleanup-20260804` with a writable basetemp outside the repository:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_avatar_qa_cleanup.py -q --basetemp C:\tmp\seolleyeon-avatar-qa-repro-20260804
```

Result: `28 passed`, exit code `0`, duration `81.64s`.

The external basetemp produced 28 PNG files and one `ttl_report.json` in non-current pytest output directories. Pytest also produced current-pointer entries. A temporary, untracked copy was made only so Reviewer B could inspect the outputs read-only; it is not part of any commit.

## Semantic regeneration

- All 34 tracked PNG files under `pytest_tmp_avatar_qa_escalated/**` have byte hashes that match one of the current test's generated PNG outputs. Repeated hashes are expected because the tests intentionally reuse the same synthetic source/pattern cases.
- The current test source creates `source.png` and `candidate.png` through `_save_png` and `tmp_path`; relevant code is in `tests/test_avatar_qa_cleanup.py:107-132`, `288-613`.
- The tracked TTL report and the externally generated TTL report are semantically equal after JSON parsing. The difference is formatting/line endings, not report content.
- Exact checked-in path recreation is not claimed: pytest creates its own temporary directory names. The evidence is semantic regeneration plus zero exact path consumers.

## Consumer search

Bounded repository search found no exact path, candidate directory path, runtime route, Firebase/Functions, CI, native, asset, fixture, golden, migration, or operational consumer. The only remaining directory mentions are analyzer/editor exclusions in `analysis_options.yaml` and `.vscode/settings.json`.

## Disposition

- Batch 002: ten regenerated source/candidate PNGs, independently reviewed and approved.
- The remaining 24 PNGs and TTL report require their own exact batch disposition; the six legacy b/p PNGs are not treated as direct current-test path recreation even though their bytes match the same synthetic generator outputs.
