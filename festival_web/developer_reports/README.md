# Festival Developer Reports

운영자가 Firebase Console에서 신고/제재 데이터를 빠르게 확인하기 위한 폴더입니다.

## Firestore 컬렉션

### 1. 사용자 신고: `festivalDeveloperReports`

앱에서 프로필/채팅 신고가 접수되면 이 컬렉션에 문서가 생성됩니다.

주요 필드:
- `status`: `open` | `reviewing` | `resolved`
- `source`: `profile_detail` | `chat_screen`
- `reason`: 신고 사유
- `reporterTicketId`: 신고한 입장 코드
- `reportedTicketId`: 신고당한 입장 코드
- `reportedProfileSnapshot`: 신고 시점 프로필 스냅샷
- `roomId`: 채팅 신고일 때만 존재
- `createdAt`

Firebase Console 경로:
`Firestore Database > festivalDeveloperReports`

정렬 추천:
- `createdAt` 내림차순
- `status == open`

### 2. 입장 코드 제재: `festivalTicketEnforcement`

부적절한 사용자를 빠르게 비활성화할 때 사용합니다.

문서 ID = 입장 코드(ticketId)

예시는 `enforcement.example.json` 참고.

```json
{
  "ticketId": "K9M2Q4",
  "disabled": true,
  "reason": "부적절한 메시지 반복",
  "disabledBy": "developer",
  "notes": "3건 신고 확인",
  "disabledAt": "서버 타임스탬프"
}
```

`disabled: true` 이면:
- 해당 코드로 새 입장 불가
- 이미 연결된 세션은 앱에서 자동 로그아웃

## 빠른 제재 방법

1. `festivalDeveloperReports`에서 `reportedTicketId` 확인
2. `festivalTicketEnforcement/{reportedTicketId}` 문서 생성/수정
3. `disabled: true` 저장
4. 해당 사용자는 즉시 입장 제한 (기존 세션도 끊김)

## 스키마

- `report.schema.json`
- `enforcement.example.json`
