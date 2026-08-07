# Full tracked-file inventory

Generated from `git -c core.quotePath=false ls-files` at the audit workspace. The machine-readable inventory is `full_file_inventory.csv` and contains 18,140 post-removal tracked paths; the pre-removal snapshot contained 18,150 paths.

## Classification counts

These are first-pass heuristic classifications used for triage. They are not deletion decisions.

| Classification | Count | Meaning |
|---|---:|---|
| GENERATED_OR_ARTIFACT | 16,614 | Build/cache/vendor/generated/temporary-like path or extension; consumer and owner audit still required |
| UNCERTAIN_OR_SEPARATE_PROJECT | 298 | Ownership, prototype, subproject, or unusual path is not proven safe to remove |
| RUNTIME_OR_PLATFORM | 646 | App, backend source, platform, or asset runtime path |
| OPERATIONAL_OR_PIPELINE | 152 | Scripts, infra, rules/config, deployment, or pipeline path |
| DOCUMENTATION | 281 | Documentation or documentation-like path |
| TEST | 149 | Tests, fixtures, or test-like path |

The generated/artifact count is intentionally conservative about names such as `.linked`, `.unlinked2`, `.digest`, `tmp`, `dist`, `coverage`, build output, dependency directories, and related extensions. A generated-looking file can still be required in the repository or referenced by a deployment/repair process.

## Top-level distribution

| Top-level path | Tracked paths |
|---|---:|
| `festival_web` | 9,869 |
| `tmp` | 5,975 |
| `.tmp` | 810 |
| `lib` | 447 |
| `docs` | 142 |
| `.agents` | 114 |
| `functions` | 99 |
| `android` | 77 |
| `scripts` | 77 |
| `test` | 58 |
| `설레연 프론트 ui 디자인` | 57 |
| `ios` | 49 |
| `tests` | 48 |
| `pytest_tmp_avatar_qa_escalated` | 45 |
| `tools` | 35 |
| `macos` | 30 |
| `SpoqaHanSansNeo_TTF_subset` | 21 |
| `windows` | 18 |
| `assets` | 15 |
| `recsys` | 13 |

Other root/config paths are included in the CSV but omitted from the compact table.

## Important ownership boundaries

- `festival_web/**` is a large first-party-looking Flutter/web project with its own source, assets, tests, scripts, tools, and AI model directories. It is not vendor output and was not deleted.
- `tmp/**` and `.tmp/**` contain reports, fixtures, scripts, and files with denied or dynamic-looking consumers. They were not cleaned.
- `seolleyeon-initial/**`, `seolleyeon-iniitial/**`, and `설레연 프론트 ui 디자인/**` are uncertain/parallel/prototype areas. Similar names alone are not proof of duplication.
- `.linked`, `.unlinked2`, `.digest`, and related generated-looking artifacts require a source/consumer/restore audit before any removal.

## CSV columns

`Path`, `Tracked`, `WorktreeExists`, `SizeBytes`, `TopLevel`, `Extension`, `Classification`, `WorkflowRelation`, `RuntimeProtection`, `ReferenceAuditStatus`, `GitHistoryStatus`, and `Notes` are present for each tracked path.

`GitHistoryStatus` means that a path appeared or did not appear in an all-refs name-only history scan. It is not a substitute for `git log --follow` on a candidate. `ReferenceAuditStatus` intentionally uses `not-proven-dead` for non-protected paths; it does not claim that every row received a complete 12-check review.

## Scope limitation

The inventory is complete for tracked paths, but a path inventory alone cannot prove runtime unreachability. The reference graph, dynamic-feature matrix, workflow reconciliation, and candidate review are required before deletion.


## Phase 2 inventory reconciliation

The original CSV is the pre-removal snapshot: 18,150 tracked rows. Batch 001 removed ten exact pointer files from the isolated cleanup branch, so the cleanup branch post-removal count is 18,140 tracked paths. The ten removed rows are listed in 08-removed-files-manifest.md and the exact evidence is frozen in 11-exact-file-review-matrix.md; the original dirty WIP checkout still retains those files by design.

full_file_inventory.csv has been reconciled for the post-Batch-001 cleanup snapshot. The retained image/report rows under pytest_tmp_avatar_qa_escalated/** remain uncertain and are not implied safe by the pointer deletion.