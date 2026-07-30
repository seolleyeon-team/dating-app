# 더미 사용자 100명 생성 - 구현 계획

## 요구사항
- Firestore `users` 컬렉션에 더미 사용자 100명 생성
- ID: 1로 시작하는 10자리 난수 (예: 1234567890)
- 템플릿: `users/4705818223` 문서 구조 참고
- photoUrls: Firebase Storage `ai_profiles/` 폴더의 사진
  - `onboarding.gender` = female → `ai_profiles/female/` 사진만
  - `onboarding.gender` = male → `ai_profiles/male/` 사진만

## 구현 단계

### 1. Firestore에서 템플릿 사용자 로드
- `users/4705818223` 문서 전체 조회
- onboarding, idealType, top-level 필드 구조 파악

### 2. Firebase Storage에서 이미지 URL 수집
- Bucket: `seolleyeon.firebasestorage.app`
- `ai_profiles/female/` 하위 파일 목록 → download URL 생성
- `ai_profiles/male/` 하위 파일 목록 → download URL 생성

### 3. 더미 사용자 데이터 생성
- 10자리 ID: `1` + random 9자리 (중복 방지)
- 템플릿 복사 후 변형:
  - nickname: 더미1, 더미2, ... 또는 랜덤 한국 이름
  - gender: 랜덤 50:50 (female/male)
  - age, height: 템플릿 기준 ±랜덤 변동
  - photoUrls: gender에 맞는 폴더에서 2~6장 랜덤 선택
- 학생 인증 등 일부 필드는 더미용으로 조정 (isStudentVerified: true)

### 4. Firestore에 배치 쓰기
- BulkWriter로 100개 문서 생성
- 기존 사용자 ID와 충돌하지 않도록 확인

## 의존성
- google-cloud-firestore
- google-cloud-stora

## 실행
```bash
cd lib/ai_recommend_model
python create_dummy_users.py --firestore_project seolleyeon --count 100
```

## 전제조건
- `GOOGLE_APPLICATION_CREDENTIALS` 환경변수 설정 (서비스 계정 JSON 경로)
- 또는 `gcloud auth application-default login` 실행
