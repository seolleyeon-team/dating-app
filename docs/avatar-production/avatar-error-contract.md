# Avatar Error Contract

Version: `avatar_error_v2`

Errors return a stable `reasonCode`, safe Korean message, retry class, and source
lock instruction. They never include exception text, private references, bucket
names, signed URLs, raw IDs, or model internals.

| Reason code | Safe message | Retry/source behavior |
| --- | --- | --- |
| `unauthenticated` | 로그인이 필요해요. | sign in; no inferred unlock |
| `app_check_required` | 앱 보안 확인에 실패했어요. 잠시 후 다시 시도해주세요. | no upload |
| `avatar_already_approved` | 아바타가 등록되어 있어요. 프로필 이미지는 삭제하거나 변경할 수 없어요. | permanently locked |
| `avatar_source_locked` | 아바타 생성이 시작되어 사진을 변경할 수 없어요. | recover current status |
| `avatar_state_inconsistent` | 아바타 상태를 확인할 수 없어요. 고객 지원이 필요해요. | fail closed; admin repair |
| `unsupported_content_type` | 지원하지 않는 이미지 형식이에요. | local selection remains editable only if no server state exists |
| `image_too_large` | 사진 용량이 너무 커요. 더 작은 사진을 선택해주세요. | same as above |
| `invalid_image` | 사진을 읽을 수 없어요. 다른 사진을 선택해주세요. | same as above |
| `avatar_source_no_face` | 얼굴을 찾지 못했어요. 얼굴이 잘 보이는 사진을 선택해주세요. | source remains locked after accepted upload; support/reset policy required |
| `avatar_source_multi_face` | 얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요. | no QA bypass |
| `avatar_source_face_too_small` | 얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요. | no QA bypass |
| `avatar_source_occluded` | 얼굴이 가려져 있어요. 얼굴이 잘 보이는 사진을 선택해주세요. | no QA bypass |
| `avatar_background_too_risky` | 배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요. | no QA bypass |
| `avatar_retry_not_allowed` | 현재 상태에서는 다시 시도할 수 없어요. | locked; support if terminal |
| `avatar_retry_limit_reached` | 다시 시도할 수 있는 횟수를 초과했어요. 고객 지원이 필요해요. | locked; terminal |
| `avatar_generation_paused` | 현재 아바타 생성을 잠시 이용할 수 없어요. | locked if source exists |
| `avatar_budget_exceeded` | 현재 아바타 생성을 잠시 이용할 수 없어요. | locked if source exists |
| `avatar_job_not_current` | 최신 아바타 생성 상태를 다시 확인해주세요. | authoritative refresh |
| `no_previewable_candidates` | 안전한 아바타 후보를 만들지 못했어요. 같은 사진으로 다시 시도해주세요. | retry only when server allows |
| `qa_requires_review` | 아바타를 안전하게 확인하고 있어요. 잠시 후 다시 확인해주세요. | no preview |
| `avatar_generation_timeout` | 아바타 생성 시간이 길어지고 있어요. 상태를 다시 확인해주세요. | authoritative refresh; no unlock |
| `internal` | 아바타 처리 중 문제가 발생했어요. 잠시 후 다시 확인해주세요. | no raw error; lock depends on authoritative status |

HTTP/Firebase error class is secondary to `reasonCode`. Failed preconditions are
used for lock/state conflicts; invalid argument for pre-storage image validation;
resource exhausted for bounded retry/budget limits; unauthenticated or permission
denied for Auth/App Check/allowlist failures.
