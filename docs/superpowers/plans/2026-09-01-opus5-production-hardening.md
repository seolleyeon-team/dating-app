# Seolleyeon Opus5 Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit the production codebase, confirm security and correctness findings with evidence, implement the smallest test-backed fixes, and produce an honest production-readiness decision without touching production systems.

**Architecture:** The audit runs from the clean `security-main` worktree and separates evidence collection from remediation. Six read-only lanes cover client, Firebase/backend, recommendations, avatar processing, operations/dependencies, and fallback/generated-code patterns; the main agent validates and deduplicates their findings before any code change.

**Tech Stack:** Flutter/Dart, Firebase Authentication/Firestore/Storage/App Check, TypeScript Cloud Functions on Node.js 22, Python recommendation and avatar workers, Firebase Emulator Suite, GitHub Actions and Cloud Build.

**Spec:** `C:/Users/samsung/.codex/attachments/6f998900-174f-40c6-a465-b08bea155777/pasted-text.txt`

## Global Constraints

- Work only on branch `security-main` in `C:/Users/samsung/StudioProjects/semisemifinal-security`.
- Do not deploy, mutate production data, alter real accounts, rotate secrets, execute migrations, trigger paid image generation, or initiate real payments.
- Never print or copy secret or PII values into output or audit documents.
- Preserve public APIs, Firestore paths, user data compatibility, core UX, and existing production fallbacks unless evidence proves a change is required.
- Use tests before security and correctness fixes, make minimal changes, and keep unrelated formatting out of commits.
- Mark every unexecuted or externally dependent verification as `BLOCKED`, `NOT_CONFIGURED`, `NOT_APPLICABLE`, or `NOT_ASSESSED` rather than claiming success.

---

### Task 1: Record safety baseline and inventory

**Files:**
- Create: `docs/audits/opus5/01-file-inventory.md`
- Create: `docs/audits/opus5/02-read-coverage.md`
- Create: `docs/audits/opus5/03-baseline-results.md`

- [ ] Verify repository root, branch, clean status, HEAD, recent commits, remotes, worktree isolation, and stash independence.
- [ ] Count tracked files by top-level directory and extension using `git ls-files`, excluding generated/dependency/cache directories from production review.
- [ ] Record all instruction files and nested scope constraints before reading production files.
- [ ] Record `.firebaserc` and `firebase.json` production-link risk without invoking Firebase services.
- [ ] Commit only the three baseline documents with `chore(audit): record codebase baseline and inventory` after their evidence is complete.

### Task 2: Execute local baseline gates

**Files:**
- Modify: `docs/audits/opus5/03-baseline-results.md`
- Create: `docs/audits/opus5/10-verification-results.md`

- [ ] Run `dart format --output=none --set-exit-if-changed .` and record the exit code.
- [ ] Run `flutter analyze` and `flutter test`; record failures without changing expectations.
- [ ] Run `npm --prefix functions ci`, `npm --prefix functions run lint`, `npm --prefix functions test`, and `npm --prefix functions run build`.
- [ ] Run Firestore and Storage rules tests only with the explicit emulator test project configured by their package scripts.
- [ ] Run repository Python tests with the configured interpreter; record unavailable tools rather than installing ad-hoc scanners.
- [ ] Run configured safe secret/security scanners and dependency audits; do not use forced dependency fixes.
- [ ] Distinguish pre-existing failures from failures caused by later changes.

### Task 3: Perform six read-only subsystem audits

**Files:**
- Create: `docs/audits/opus5/04-security-findings.md`
- Create: `docs/audits/opus5/05-correctness-findings.md`
- Create: `docs/audits/opus5/06-performance-findings.md`
- Create: `docs/audits/opus5/07-fallback-inventory.md`

- [ ] Trace Flutter authentication, onboarding, profile/privacy, matching, chat, reporting, blocking, lifecycle, and native configuration.
- [ ] Trace Firestore/Storage rules against real client queries and Functions authorization, validation, App Check, rate limits, idempotency, and logging.
- [ ] Trace recommendation inputs, filtering, model artifacts, deterministic ranking, retries, partial results, and persistence contracts.
- [ ] Trace avatar upload, consent, storage, provider transport, moderation, cost controls, retries, QA, and cleanup.
- [ ] Inspect dependency, CI/CD, Cloud Build/Run, monitoring, rollback, and supply-chain configuration.
- [ ] Classify mocks, placeholders, swallowed errors, fallbacks, dead code, duplicate helpers, and generated-code artifacts.
- [ ] Re-open every P0/P1 candidate in the main session and record exact file and line evidence before accepting it.

### Task 4: Triage and freeze remediation scope

**Files:**
- Create: `docs/audits/opus5/00-executive-summary.md`
- Create: `docs/audits/opus5/08-remediation-plan.md`
- Create: `docs/audits/opus5/11-residual-risks.md`

- [ ] Deduplicate findings and assign IDs, severity, impact, exploit conditions, root cause, confidence, proposed test, compatibility impact, rollback, and owner.
- [ ] Separate confirmed evidence from inference and unknown external state.
- [ ] Order remediation by P0, P1, correctness/data consistency, fallback safety, measured performance, dependency/CI, and low-risk cleanup.
- [ ] Stop and request approval for production mutations, destructive migrations, secret rotation, legal/policy decisions, real notifications, payments, or paid API calls.

### Task 5: Implement confirmed fixes with TDD

**Files:**
- Modify only files named by accepted findings in `docs/audits/opus5/08-remediation-plan.md`.
- Add focused tests adjacent to the affected Flutter, Functions, rules, Python, or integration test suites.
- Modify: `docs/audits/opus5/09-change-log.md`

- [ ] For each accepted finding, add the smallest reproduction test and run it to confirm the expected failure.
- [ ] Implement the minimal compatible fix without broad rewrites or unrelated formatting.
- [ ] Run the focused test, neighboring regression tests, and the relevant static/build gate.
- [ ] Review the diff for secrets, PII, generated artifacts, and unrelated user changes.
- [ ] Commit each independently testable fix with a specific conventional commit message and record its SHA.

### Task 6: Verify production readiness and rollback

**Files:**
- Modify: `docs/audits/opus5/00-executive-summary.md`
- Modify: `docs/audits/opus5/09-change-log.md`
- Modify: `docs/audits/opus5/10-verification-results.md`
- Modify: `docs/audits/opus5/11-residual-risks.md`
- Create: `docs/audits/opus5/12-production-readiness.md`
- Create: `docs/audits/opus5/13-deployment-and-rollback.md`

- [ ] Re-run formatter, analyzer, Flutter tests/builds, Functions gates, rules emulator tests, Python tests, safe security scans, and Git diff/status checks.
- [ ] Record every command, working directory, duration, exit code, result, failure cause, baseline relationship, and blocker status.
- [ ] Assign `READY`, `READY_WITH_CONDITIONS`, `NOT_READY`, or `NOT_ASSESSED` to every requested subsystem using only verified evidence.
- [ ] Document ordered deployment prerequisites and per-commit rollback commands without deploying.
- [ ] Run a final security review and code review, resolve confirmed regressions, and report remaining risks honestly.
