# Independent CLIP private-media security review

검증일: 2026-09-02 (Asia/Seoul)

## Review identity and scope

- reviewer: `focused_security_diff_review` (Newton), 독립 code-review subagent
- base SHA: `e5b47c84161ea8cc7a4236925eff8971e7d0cc4e`
- final reviewed scope: 11 modified runtime/test files와 신규 감사 문서
- final verification: `git diff --check`, Python AST, JS syntax, focused pytest `19 passed`

주요 검토 파일:

- `lib/ai_recommend_model/seolleyeon_clip_embedder.py`
- `lib/ai_recommend_model/seolleyeon_clip_job_handler.py`
- `tests/test_avatar_media_privacy.py`
- `tests/test_clip_job_handler.py`
- `test/firestore_rules/authz_hardening_rules.test.js`
- `test/firestore_rules/bamboo_counter_rules.test.js`
- `test/firestore_rules/kakao_login_rules.test.js`

## Findings and closure

| ID | Severity | Finding | Closure | Final |
|---|---|---|---|---|
| CLIP-R1 | HIGH | authoritative private-media document의 GCS object path가 payload UID에 바인딩되지 않음 | `_parse_gcs_uri()` 후 `users/{uid}/source/` prefix와 non-directory object를 강제. cross-user RED/GREEN 추가 | RESOLVED |
| CLIP-R2 | MEDIUM | 최초 allowlisted HTTPS host 검사 후 Requests 기본 redirect를 따라가면 후속 hop이 재검증되지 않음 | `allow_redirects=False`, 모든 3xx를 body 처리 전에 거부. metadata-address Location RED와 정상 200 GREEN 추가 | RESOLVED |

최종 미해결 P0/P1 finding은 0개다.

## Security boundary disposition

| Boundary | Evidence | Disposition |
|---|---|---|
| SSRF / scheme | HTTPS만 허용; signed/private/temp marker는 network 전에 거부 | PASS |
| Host allowlist | 최초 HTTPS host exact allowlist | PASS |
| Redirects | 자동 follow 비활성화; 3xx fail closed | PASS |
| GCS allowlist | final private-source bucket allowlist, 명시적 empty도 deny | PASS |
| Object ownership | object path가 authoritative payload UID prefix에 속해야 함 | PASS |
| Byte limit | Content-Length와 실제 streamed/downloaded bytes 모두 제한 | PASS |
| Consent/status | authoritative `userPrivateMedia/{uid}`의 consent, active status, requested ID만 선택 | PASS |
| Logging/privacy | private refs와 exception output을 redaction helper로 처리 | PASS |
| Cross-user isolation | cross-user path는 embedding 전 거부되고 failed state만 기록 | PASS |
| Project isolation | 명시된 Firestore project와 final bucket 경계 밖 source는 허용하지 않음 | PASS |

## TDD evidence

- historical CLIP GCS wiring reversal: exact RED 재현
- private GCS/signed HTTPS initial focused subset: `12 passed, 40 deselected`
- cross-user source path: pre-fix `DID NOT RAISE`, post-fix PASS
- redirect chain: pre-fix redirect body까지 도달해 RED, post-fix 302 deny + 200 decode `2 passed`
- final related P1 subset: `15 passed, 47 deselected`
- independent final focused suite: `19 passed`

## Final disposition

```text
INDEPENDENT_SECURITY_REVIEW = PASS
UNRESOLVED_P0 = 0
UNRESOLVED_P1 = 0
REDIRECT_FINDING = RESOLVED
```
