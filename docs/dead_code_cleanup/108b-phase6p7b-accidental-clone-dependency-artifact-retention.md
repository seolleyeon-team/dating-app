# Phase 6P-7B accidental-clone dependency artifact retention

Status: `ACCIDENTAL_CLONE_DEPENDENCY_ARTIFACTS_PRESERVED`.

The Phase 7B hard gates first stopped on an unexpected modified lockfile and
then on a second dependency-source divergence. The owner decision is to retain
both files as forensic/recovery evidence, never merge them into the clean WIP,
and delete the accidental clone only after the complete clone recheck passes.

## Source and retained artifact

- Source clone: `C:/Users/samsung/StudioProjects/semisemifinal/dating-app`
- Retained root:
  `C:/tmp/seolleyeon-phase6p7b-retained-artifacts-20260806-223836`
- Classification: `OWNER_APPROVED_ACCIDENTAL_CLONE`
- Owner disposition: `PRESERVE_DEPENDENCY_CONFIGURATION_THEN_DELETE_CLONE`

| File | Source SHA-256 | Retained SHA-256 | Clean WIP SHA-256 | Merged into active WIP |
|---|---|---|---|---|
| `pubspec.yaml` | `AD96499A...A5566C` | `AD96499A...A5566C` | `B994A89D...E113C` | NO |
| `pubspec.lock` | `D1ABDDF0...B7871` | `D1ABDDF0...B7871` | `007BE3F8...996D83` | NO |

The retained files are byte-for-byte equal to their source counterparts. Full
hashes and source-state metadata are stored in the external manifest; this
document does not copy the dependency-file contents.

## Diff and divergence checks

- YAML and lockfile diffs against clean WIP were preserved externally.
- `pubspec.yaml` and `pubspec.lock` are intentionally not applied to active or
  clean WIP.
- `public/invite-friend.html` matches active/clean WIP and is not retained as a
  unique recovery artifact.
- The clone had two tracked modified status entries and no untracked files;
  the only unique dependency configuration is the YAML/lock pair.
- The clean WIP was not modified during preservation.
- Retained-artifact scan found zero email-like values, phone-like values,
  credential assignments, and known sensitive target-name occurrences.

## Preservation gate

```text
YAML external copy: PASS
LOCK external copy: PASS
YAML SHA integrity: PASS
LOCK SHA integrity: PASS
YAML diff preserved: PASS
LOCK diff preserved: PASS
Source-state/manifest: PASS
Clean WIP untouched: PASS
Additional unique clone files: 0
Known sensitive recovery data copied: NO
```

The previous blockers are resolved by external forensic preservation. The
accidental clone remains pending the final pre-delete recheck and has not been
deleted yet.
