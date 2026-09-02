# Latest main integration

검증일: 2026-09-02 (Asia/Seoul)

## 기준선

| Item | Value |
|---|---|
| 원본 보존 worktree | `C:/Users/samsung/StudioProjects/semisemifinal-security` |
| 원본 branch | `security-main` |
| old security HEAD | `5ea0d8c1d23d2ca43584c0e262b4e4457985e123` |
| latest `github/main` | `e5b47c84161ea8cc7a4236925eff8971e7d0cc4e` |
| ahead / behind | `0 / 5` |
| merge base | old security HEAD와 동일 |
| 통합 worktree | `C:/Users/samsung/StudioProjects/semisemifinal-security-integration` |
| 통합 상태 | latest main에서 detached HEAD |

원본 `security-main`은 다른 worktree에서 사용 중이었으므로 checkout하거나 강제로 이동하지 않았다. 원본의 tracked WIP와 untracked 감사 문서는 그대로 보존했다.

## 새 upstream commits

1. `5c1d7806` — `feat(auth): make terms acceptance a server-verified gate`
2. `7479e500` — `fix(auth): order the onboarding gates and close the release bypass`
3. `3a1f40b0` — `test(auth): pin the gate order, terms authority, and release entry matrix`
4. `8a4e984d` — `fix(auth): recover from a rejected email-link terms proof`
5. `e5b47c84` — PR #68 merge

latest main delta는 auth/onboarding 중심 32개 파일이다.

## overlap 및 semantic review

- 원본 uncommitted WIP 5개 tracked 파일과 latest-main 32개 변경 파일의 직접 file overlap은 0개였다.
- semantic overlap은 latest main의 `firestore.rules` canonical session/onboarding 보호와 WIP의 Rules fixture assertions였다.
- 현재 Rules helper의 `get()` + `after.diff(before)` 계약과 canonical custom claim fixture는 양립한다.
- CLIP private-media source/job 경로는 latest auth 변경에서 수정되지 않았다.
- merge conflict, content conflict, unresolved semantic conflict는 없었다.

## integration method

1. latest `github/main` SHA를 고정했다.
2. 해당 SHA에 새 detached worktree를 만들었다.
3. 원본 WIP의 5개 tracked 파일을 byte-equivalent로 이식했다.
4. 기존 untracked 감사/계획 문서를 복사했다.
5. 통합 worktree에서만 TDD 수정과 전체 검증을 수행했다.

브랜치 강제 전환, reset, stash, rebase, commit, push는 하지 않았다.

## P1 preservation

- private GCS loader wiring과 signed/private HTTPS pre-network rejection을 latest main 위에서 다시 RED/GREEN 검증했다.
- reviewer가 발견한 cross-user object path 경계와 redirect-chain 경계도 통합 worktree에서 추가로 닫았다.
- production Rules, auth schema, queue payload schema, public API는 완화하거나 변경하지 않았다.

결론: `LATEST_MAIN_INTEGRATED = YES`.
