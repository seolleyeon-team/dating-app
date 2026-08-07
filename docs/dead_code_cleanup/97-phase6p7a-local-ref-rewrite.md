# Phase 6P-7A local ref rewrite rehearsal

Mode: LOCAL_SANITIZATION_REHEARSAL_ONLY.

No original source/WIP state, Git ref, stash, reflog, remote, or filesystem copy
was modified or deleted. Phase 7A evidence documents were added/updated in the original workspace as requested. The rewrite was performed only in the isolated Phase
7A candidate under C:/tmp/seolleyeon-phase6p7a-20260806-172208.

## Attested method

The accepted Method B one-to-one Git DAG rewriter was used.

- Script: C:/tmp/seolleyeon-phase6p6r2-20260806-002233/method-attestation/rewrite_git_dag_one_to_one.py
- SHA-256: 8DB6852C45FF47F64E7D571320DFA3F0CA99C01D48E766E32604CB11CF42A256
- Target path: .tmp/email_tokens_sample.json
- Known sensitive blob: 29a6db3aed274bc3ef622c3146795e504da16b03
- Raw target contents were never logged, copied, or included in evidence.

The source mirror was an independent no-hardlinks mirror of the original local
repository. The candidate was written from that mirror; the original object
database was not opened for mutation.

## Result

| Check | Result |
|---|---:|
| Source reachable commits | 291 |
| Sanitized reachable commits | 291 |
| Source merges | 84 |
| Sanitized merges | 84 |
| Mapping entries | 291 |
| Unique new commits | 291 |
| Lost commits | 0 |
| Collapsed commits | 0 |
| Parent count/order/arity mismatches | 0 |
| Topology fingerprint difference | 0 |
| Non-target tree differences | 0 |
| Allowed target deletions | 65 |
| Sensitive path reachable in candidate | 0 |
| Known blob reachable in candidate | 0 |
| Metadata mismatches | 0 |
| Source refs | 65 |
| Candidate refs | 65 |
| Ref-name/type/tip mismatches | 0 |
| Commit refs mapped | 64 |
| Direct clean tree refs preserved | 1 |

The one direct tree ref under refs/codex/turn-diffs/checkpoints/ was not a
commit and did not contain the target; it was preserved as a clean direct tree
ref. All 64 commit refs, including local branches, remote-tracking refs, stash,
backup refs, and other recovery refs, resolve through the one-to-one mapping.

## Fresh clean recovery

The intermediate candidate still physically contains the old Git object in its
copied object database, but the object is unreachable. A fresh no-local clone
was then created at:

C:/tmp/seolleyeon-phase6p7a-20260806-172208/candidate/clean-local-recovery.git

The fresh clone has 65 refs, 291 commits, and 84 merges; the sensitive path has
zero history/reachability and the known blob is physically absent. git fsck
--full --connectivity-only --no-dangling produced zero errors.

This is a rehearsal replacement, not an in-place rewrite. The intermediate
source/candidate mirrors remain retained as security evidence pending a
separate Phase 6P-7B approval.


