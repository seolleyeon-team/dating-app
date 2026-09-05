> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md).
>

# 아바타 이미지 생성 파이프라인 품질·MAI Image 2.5 도입 분석 보고서

Date: 2026-07-31  
Status: read-only analysis (코드 변경 없음)  
Scope: 현재 저장소의 생성 경로 + staging 7인/56후보 forensic 기록 + MAI-Image-2.5 공개 스펙

---

## 0. 한 줄 결론

**“Flux가 구려서 원본과 다르게 나온다”는 가설은 부분적으로만 맞다.**  
Flux.2-klein-4B(4B, 4 steps)의 약한 조건 추종력은 **기여 요인**이지만, 저장소·staging 증거가 가리키는 **1차 원인은 생성 직전에 얼굴 정보를 거의 지워 버리는 privacy reference preprocess**이다. MAI Image 2.5로 모델만 교체하고 기존 `privacy_strict` 입력을 그대로 넣으면 닮음 문제는 재발할 가능성이 높다. 반대로 원본 사진+프롬프트만 남기고 파이프라인을 폐기하는 것도 제품의 비식별 아바타 계약·MAI 정책과 충돌한다.

**권고: 하이브리드.**  
업로드·동의·admission·안전/식별상한 QA·승인/보관 골격은 유지하고, **생성 코어만** MAI edits API + (재설계된) 제한적 참조 이미지 + 짧은 스타일 프롬프트로 교체한다. Flux 로컬 GPU 경로·Florence trait 복원 의존·과한 face downsample은 생성 경로에서 폐기 대상으로 본다.

---

## 1. 질문 재진술

1. 아바타 생성 파이프라인을 한 단계씩 따라가며 품질이 안 나오는 이유와 불필요 과정을 파악한다.  
2. “주 원인이 Flux 성능”이라는 판단을 검증/반박한다.  
3. 모델 외 품질 저하 요인을 기록한다.  
4. MAI Image 2.5 도입 시 (A) 기존 파이프라인 유지 + Flux→MAI API만 교체 vs (B) 파이프라인 폐기 후 원본+프롬프트만 전달 중 무엇을 택할지 총체 판단한다.

---

## 2. Flux 가설에 대한 판정

### 판정 요약

| 주장 | 판정 | 신뢰도 |
|------|------|--------|
| Flux가 원본과 다른 얼굴을 만드는 데 기여한다 | **부분 채택** | High |
| Flux가 **유일한/주된** 원인이다 | **기각** | High |
| 모델 교체만으로 품질이 해결된다 | **기각(조건부)** | High — 현재 reference가 유지되면 |
| 더 큰/강한 모델(MAI 20B, edits)이 도움이 될 수 있다 | **채택 가능** | Medium — A/B 필요 |

### Evidence (저장소·기존 RCA)

1. **생성 모델은 소형·저스텝 설정**
   - 모델: `black-forest-labs/FLUX.2-klein-4B` (`lib/ai_recommend_model/avatar_generation/__init__.py`)
   - 기본값: 1024×1024, `num_inference_steps=4`, `guidance_scale=1.0` (`flux_config.py:9-12`)
   - `strength` / ControlNet / IP-Adapter 미사용 (`worker.py:1304-1313`)
   - Prompt builder도 동일 4-step을 recommended로 고정 (`seolleyeon_avatar_prompt_builder_v4.py:226-228`)

2. **Flux에는 원본이 아니라 privacy-reduced 이미지가 들어간다**
   - 기본 프로필 `privacy_strict`: face equivalent **28px**, blur **4.5** (`preprocessing/reference.py:35-45`)
   - 크롭 후 원본 캔버스 크기로 LANCZOS 업샘플 (`reference.py:282`)
   - 제품 불변조건 문서: “no raw source passed to FLUX” (`avatar-fidelity-root-cause-plan-20260729.md`)

3. **Staging human review (7명, 56후보)**
   - 명확/대체로 타인 인상: **54/56**
   - 닮음 5점 만점 분포: 1점 14, 2점 31, 3점 9, 4점 2, 5점 0
   - 공통 결함: 제네릭·과도 스무딩·눈 확대·턱/볼 구조 소실·피부톤/성인감 drift
   - RCA 의사결정 행렬에서 `PRIVACY_REFERENCE_OVER_BLUR` = **primary / high**, `FLUX_CONFIG_LOW_FIDELITY` = **probable / medium**, `TRAIT_EXTRACTION_LOSS` = **primary / high**

4. **Extra round(추가 4장)도 동일 preprocess를 재사용해 닮음을 개선하지 못함** — 모델 랜덤성만으로는 해결되지 않았다는 간접 증거.

### Inference

- Flux klein 4B + 4 steps는 강한 아바타/아이돌 스타일 prior에 대해 **참조를 강하게 붙잡지 못하는 구조**다. 사용자 직관(“모델이 구리다”)은 이 구간에서는 타당하다.
- 그러나 입력 얼굴이 이미 28px급 blob이면, **어떤 생성 모델도 원본 이목구비를 복원할 수 없다.** 따라서 “Flux만 바꾸면 된다”는 인과 단순화는 틀렸다.
- 더 정확한 인과 사슬:

```
원본 JPEG(이미 EXIF strip/Q92)
  → (종종) 작은 얼굴 / 전신 작업 이미지
  → privacy_strict face 28px + blur 4.5  (+ 배경 중화)
  → trait card는 대부분 unclear (복원 실패)
  → 긴 privacy/anti-beauty 프롬프트가 남은 약한 신호와 경쟁
  → Flux.2-klein-4B @ 4 steps / guidance 1.0 이 제네릭 prior로 채움
  → QA는 “너무 닮음” 상한만 있고 “너무 안 닮음” 하한이 없음
  → 다른 사람처럼 보이는 예쁜 아바타가 preview까지 못 가거나, 가도 품질 불만
```

### Unknowns

- Diffusers `Flux2KleinPipeline`의 `image=`가 내부적으로 어떤 conditioning strength를 쓰는지(문서화되지 않은 동작).
- 현재 배포 revision의 `AVATAR_REFERENCE_PROFILE`가 코드 기본(`privacy_strict`)과 동일한지(문서상 staging은 region_privacy_v1 / privacy 경로로 기록; 코드 기본 face 28px는 문서의 구 64px보다 더 공격적).
- MAI edits가 “스타일 변환 + 부분 비식별” 프롬프트에서 실제 생체 식별 잔존을 얼마나 남기는지 — **반드시 실측 A/B 필요**.

---

## 3. End-to-end 파이프라인 (단계별)

| # | 단계 | 위치 | Flux 입력에 미치는 영향 | 품질 영향 |
|---|------|------|-------------------------|-----------|
| 1 | 온보딩 사진 선택 | `photo_upload_screen.dart` | 없음 | 원본 구도/조명 품질이 상한선 |
| 2 | Callable 업로드 | `avatar_source_photo_service.dart`, `avatarMedia.ts` | 저장 바이트 결정 | — |
| 3 | Auth/consent/approved-lock | `avatarMedia.ts` | 없음 | 운영 안전 |
| 4 | EXIF strip + JPEG Q92 + flatten white | `avatarMedia.ts` `stripExifAndNormalizeImage` | worker가 받는 이미지 | **경미** 고주파 손실 |
| 5 | Private GCS + `avatarJobs` | `avatarMedia.ts` | 없음 | — |
| 6 | Cloud Tasks → worker | `avatarMedia.ts` enqueue | 없음 | — |
| 7 | Worker 수신/계약 검증 | `worker_service.py`, `worker.py` | 없음 | — |
| 8 | Source load RGB | `worker.py` | 분석·참조 원천 | — |
| 9 | Small-face 분석·blur admission | `analysis/small_face/*` | 생성 직전 입력은 아님(admission/trait) | 나쁜 소스는 차단(품질↑), 과도 차단 시 실패↑ |
| 10 | Visual risk (logo/text) | `worker.py` | 영역 마스킹에 사용 | 누수 방지; 실패 시 메타만 있고 실제 중화 부족할 수 있음(RCA) |
| 11 | **Reference preprocess → generation_image** | `preprocessing/reference.py` | **이것이 Flux `image=`** | **치명적 닮음 손실 (1차)** |
| 12 | Florence-2 trait card | `florence2.py`, `trait_card/*` | 프롬프트 JSON | 복원 실패 시 **2차** 정보 공백 |
| 13 | Prompt build v4 | `seolleyeon_avatar_prompt_builder_v4.py` | Flux `prompt` | 긴 privacy 문구·토큰 예산 경쟁 (**2~3차**) |
| 14 | Adaptive plan (기본 4장) | `adaptive_generation.py` | 후보 수 | 비용; 품질 상한은 동일 경로 |
| 15 | **FLUX generate** | `worker.py` Flux2Klein | 최종 픽셀 | **모델/설정 기여 (3차, 그러나 실재적)** |
| 16 | 후보 업로드 | temp GCS | — | — |
| 17 | QA + fidelity shadow | `qa.py`, `fidelity_corridor.py` | 미리보기 게이트 | 하한 없어 “안 닮은 예쁨” 통과 가능; staging은 모델 unavailable로 0 preview |
| 18 | Extra round (조건 시 +4) | `worker.py` | **같은 privacy image 재사용** | **낭비에 가깝다(닮음 개선 증거 없음)** |
| 19 | Preview/rerank/terminal | `preview_policy.py`, `rerank.py` | — | 품질 생성과 무관, 노출 정책 |
| 20 | Client poll / approve | Functions + Flutter | — | — |

---

## 4. 품질을 떨어뜨리는 요인 순위

| Rank | 요인 | 유형 | 신뢰도 | 근거 |
|------|------|------|--------|------|
| 1 | `privacy_strict` face 28px + blur 4.5 | Evidence+Inference | High | 코드 기본값; RCA primary; human 54/56 타인 |
| 2 | Trait card 광범위 `unclear` → 프롬프트가 얼굴을 복원하지 못함 | Evidence | High | 7/7 live trait 대부분 unclear; consistency ≤0.25 |
| 3 | Flux.2-klein-4B + 4 steps + guidance 1.0 + strength 없음 | Evidence+Inference | Medium–High | 설정 코드; RCA “probable”; 강한 제네릭 prior |
| 4 | Primary crop → 원본 해상도 LANCZOS 업샘플 | Evidence | Medium | `reference.py:282`; 보간 아티팩트 + face scale 왜곡 |
| 5 | 긴 privacy/anti-beauty 프롬프트 vs sparse fidelity | Evidence | Medium–High | ~618 words vs recommended max_seq 512; worker가 max_seq 미전달 |
| 6 | Analysis ref와 Generation ref 비대칭 | Evidence | Medium | trait는 더 선명한 analysis 쪽, Flux는 blur 쪽 |
| 7 | QA에 resemblance lower bound 없음 (corridor shadow) | Evidence | High | `fidelity_corridor` default shadow/uncalibrated |
| 8 | Extra round가 동일 입력 재사용 | Evidence | High | 56후보 RCA; adaptive fidelity retry는 프로덕션 미연결 |
| 9 | Staging QA 모델 unavailable + heuristic 계약 충돌 | Evidence | High | 0 preview; softPass vs previewAllowed 모순 (품질 인식/운영에 영향) |
| 10 | Upload JPEG Q92 | Evidence | Low–Medium | 경미 |
| 11 | SAM 비활성 / segmentation fallback | Evidence | Medium | 배경/타인 영역 0 메타 vs 실제 누수 후보 |

**사용자 가설 위치:** Rank 3에 해당. 중요하지만 Rank 1·2가 선행한다.

---

## 5. 불필요·낭비·오해 유발 과정

아래는 “삭제하라”는 구현 지시가 아니라, **현재 목적(닮은 비식별 아바타)** 대비 효용/비용 평가다.

| 항목 | 평가 | 이유 |
|------|------|------|
| Extra generation round (동일 privacy ref) | **낭비에 가까움** | 닮음 개선 증거 없음; 비용·시간만 증가 (staging 28/56이 extra) |
| Florence trait → Flux 텍스트 복원 경로 | **현재 효용 낮음** | live에서 핵심 얼굴 trait가 unclear; 정보를 못 살림 |
| `identity_strength_target` 후보 variant 메타 | **데드 노브** | Flux strength에 연결되지 않음 |
| `adaptive_retry_enabled` fidelity retry | **프로덕션 미연결** | 테스트에만 true |
| Env `AVATAR_REFERENCE_FACE_*` vs profile 필드 | **오해 유발** | 메타/config와 실제 픽셀 경로 불일치 가능 |
| `background_blur_radius` / desaturate 일부 | **메타성** | 실제 중화는 solid color composite 중심 |
| Fidelity corridor shadow | **품질 개선에 아직 기여 0** | 관측만; preview 결정에 미적용 |
| 로컬 GPU Flux 워밍/콜드로드 | **운영 비용** | cold model-load ~274s 기록; API 모델이면 구조 자체가 바뀜 |
| 이중 crop 체계 (small-face 512/768 vs generation crop) | **복잡도↑ / 정합↓** | trait와 generation 정보 비대칭의 온상 |

**유지 가치가 큰 것 (폐기 비권고):**

- EXIF strip / private GCS / consent / approved lock  
- Blur/admission hard reject (너무 흐린 소스 차단)  
- Background/secondary-face/text 중화 의도 (구현 품질은 별개)  
- Identity **upper bound** QA (너무 식별되는 후보 차단)  
- Approval → public 복사 분리  
- Source retention / terminal state sync 계약  

---

## 6. MAI Image 2.5 팩트 (외부 스펙)

출처: [MAI-Image-2.5 Model Card (Microsoft, 2026-06-02)](https://microsoft.ai/pdf/MAI-Image-2.5-Model-Card.PDF), [Azure Foundry MAI image how-to](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-image)

| 항목 | MAI-Image-2.5 | 현재 Flux.2-klein-4B |
|------|---------------|----------------------|
| 파라미터 | **20B** (non-embedding) | **4B** |
| 모드 | text-to-image **+ image-to-image edits** | Diffusers 로컬, `image=` conditioning |
| 컨텍스트 | **32K tokens** | 권장 max_seq 512 (실제 미전달) |
| 출력 | PNG, ≤1,048,576 px (≈1024²) | 1024² |
| 배포 | Azure AI Foundry managed API | Cloud Run GPU self-host |
| 강점(카드) | photoreal/portrait/editing/consistency | 빠른 저스텝 로컬 추론 |
| Out-of-scope | **실존 인물 사칭/기만 목적 생성 금지** | (자체 정책과 별개) |

API 형태:

- Generations: `.../mai/v1/images/generations` (prompt only)
- Edits: `.../mai/v1/images/edits` (multipart `image` + `prompt`)

아바타 use-case에는 **Edits**가 본질적으로 맞다. Generations만 쓰면 참조 얼굴이 아예 없다.

---

## 7. 전략 비교: A vs B vs C(하이브리드)

### A. 기존 파이프라인 유지 + Flux만 MAI API로 교체

**의미:** Cloud Run GPU의 `Flux2KleinPipeline` 호출만 Azure MAI edits/generations로 바꾸고, privacy preprocess·Florence·긴 프롬프트·QA·extra round는 그대로.

| 장점 | 단점 |
|------|------|
| 변경 표면 최소, 승인/보관/동의 계약 유지 | **Rank 1 원인(28px blur) 미해결** → 닮음 실패 재발 가능 |
| GPU 워커 콜드스타트/가중치 관리 부담 감소 | Florence+긴 프롬프트 비용/복잡도 잔존 |
| QA/preview 골격 재사용 | MAI edits에 blur blob을 넣으면 “정밀 편집” 강점이 사장됨 |
| | 모델 비용/쿼터·데이터 거주(Azure)·PII가 외부로 나감 |

**판정:** **비권고(단독).** “모델만 바꾸면 된다”는 사용자 직관의 구현형이지만, 증거상 실패 모드를 재현한다.

### B. 파이프라인 폐기 + 원본 사진 + 아바타 프롬프트만 전달

**의미:** admission/trait/privacy preprocess/QA 대부분 제거. 원본(또는 upload JPEG)과 “3D 아바타로” 류 프롬프트만 MAI에.

| 장점 | 단점 |
|------|------|
| 정보 손실 최소 → 닮음 최대화 가능 | **제품 불변조건 위반**: raw source를 생성 모델에 직접 투입 (RCA가 명시적으로 금지) |
| 복잡도·지연 급감 | **식별 아바타 / 생체 복제** 위험 → dating app 프라이버시 사고 |
| MAI portrait/edit 강점 최대 활용 | Model card out-of-scope: impersonation/deceive |
| | 배경 인물·로고·학교 엠블럼 누수 방어 상실 |
| | childlike/beautification/too_identifiable 게이트 상실 시 규제·브랜드 리스크 |
| | 업로드·승인·retention을 같이 버리면 보안 후퇴 |

**판정:** **비권고(그대로의 B).** 품질만 보면 매력적이나, 설레연 아바타의 존재 이유(비식별·스타일화)와 충돌한다.

### C. 하이브리드 (권고)

**유지:**  
클라이언트 업로드 → private 저장 → consent/lock → (가벼운) admission/blur gate → **완화된/재설계된 reference** → MAI **edits** API → identity upper-bound + safety QA → preview/approve/retention.

**폐기/축소 (생성 코어 한정):**  
로컬 Flux GPU 경로, 4-step/klein 특화 설정, Florence trait를 닮음의 주채널로 쓰는 경로, 동일 입력 extra round, 28px `privacy_strict`를 기본으로 두는 생성 입력.

**생성 입력 원칙 (분석 권고, 구현 지시 아님):**

1. MAI에는 **edits** 사용 (generations-only 금지).  
2. 참조는 “원본 전체”가 아니라 **head-shoulders crop + 배경/타인/로고 중화 + 피부 미세정보/유니크 마크 억제** 수준.  
   - 현 `fidelity_balanced`(face ~40px)조차 공격적일 수 있음 → MAI용 새 프로필이 필요할 가능성 큼.  
3. 프롬프트는 **짧고 스타일 중심** (“성인 3D 아바타, 중립 배경, 로고 금지, 과도 보정 금지”).  
   - 32K 컨텍스트가 있어도, 긴 금지 나열은 스타일 prior만 키울 수 있음.  
4. Trait card는 optional diagnostic으로 강등하거나, 안경/수염/머리색 같은 **이산 안전 속성만** 유지.  
5. QA: privacy **상한**은 유지·강화, fidelity **하한**은 shadow→calibration 후 활성화.  
6. 외부 API로 원본/참조가 나가므로: retention, 암호화 전송, 로그 금지, Azure 지역/약관 검토 필수.

**왜 A/B보다 C인가 (추론):**

- A는 원인 Rank 1을 건드리지 않아 **실패를 비싼 모델로 재현**할 위험이 큼.  
- B는 닮음은 좋아져도 **제품·정책·법적 리스크가 품질 이득을 상회**.  
- C는 MAI의 edits/portrait 강점을 쓰면서도 “아바타 ≠ 실사 복제” 계약을 지킬 수 있는 유일한 균형점.

---

## 8. “충분한 추론”에 따른 최종 판단

### 품질 실패의 본질

이 시스템은 **의도적으로 얼굴을 지운 뒤**, **텍스트로 다시 그리게** 설계되어 있다.  
그런데 텍스트(trait)가 비어 있고, 그리는 모델(Flux klein 4B @ 4 steps)은 빠른 제네릭 prior가 강하다.  
결과는 “예쁜 다른 사람”이다. 사용자 불만과 staging 54/56 타인 인상이 일치한다.

### Flux에 대한 공정한 평가

- **맞다:** 현재 선택·설정은 고유사도 유지에 불리한 소형·저스텝 모델이다. MAI 20B edits는 모델 계층에서 명백히 상위 후보.  
- **틀리다/불완전:** “원본과 다르게 나오는 이유가 Flux라서”만은 아니다. **원본이 Flux에 도달하기 전에 이미 다른 정보가 된다.**

### MAI 도입 시 가장 큰 함정

1. **A형 교체**로 만족하고 preprocess를 그대로 두면 ROI 없음.  
2. **B형 원본 직투입**으로 품질 쇼를 만들면 privacy 사고로 제품을 위협.  
3. MAI 정책의실존 인물 사칭 금지**)과 제품 카피(“본인 아바타”) 사이의 법적/약관 해석을 엔지니어링 전에 확정해야 함.  
4. GPU Cloud Run → Azure API는 **비용·지연·장애·데이터 국경**이 바뀌는 아키텍처 변경이지 “한 줄 URL 교체”가 아님.

### 권고 결정

| 선택지 | 결정 |
|--------|------|
| A. 파이프라인 유지 + Flux→MAI만 | **기각(단독)** |
| B. 파이프라인 폐기 + 원본+프롬프트 | **기각** |
| C. 골격 유지 + 생성 코어·참조·프롬프트 재설계 후 MAI edits | **채택 권고** |

**성공 조건(분석 게이트, 구현 전):**

1. Exact-consent 소수 소스에서 A0(현재)/C1(MAI+완화 참조)/C2(MAI+강한 참조) 1변수 A/B.  
2. Human resemblance ≥3/5 비율과 identity-risk(너무 식별) 비율을 동시에 측정.  
3. 배경 인물·로고·childlike·beautification hard veto 유지.  
4. Corridor lower bound는 calibration 전에는 shadow.  
5. Azure로 나가는 이미지의 최소 필요성·보관 금지·지역을 문서화.

코드 변경·배포·실생성은 본 보고서가 **승인하지 않는다.**

---

## 9. Evidence / Inference / Unknown 경계

### Evidence
- Flux 모델 ID, 4 steps, guidance 1.0, strength 없음  
- privacy_strict 28px/4.5, crop upsample  
- Flux에 privacy image 전달  
- Staging 56후보 human review 및 RCA 행렬  
- Fidelity corridor shadow, adaptive fidelity retry 미연결  
- MAI 20B, edits API, 32K context, impersonation out-of-scope  

### Inference
- Rank 1이 privacy preprocess인 이유(정보량 파괴 → prior 지배)  
- A 단독 실패 재현 가능성  
- B의 정책/제품 충돌  
- C가 유일 균형점  

### Unknown
- MAI edits의 실제 닮음/식별 잔존 곡선  
- 배포 env의 현행 profile 수치  
- Flux `image=` 내부 strength  
- Azure 가격·RPM·한국 리전·약관 최종 해석  

---

## 10. 참고 산출물

- `docs/avatar-production/avatar-fidelity-root-cause-plan-20260729.md`  
- `docs/avatar-production/avatar-quality-20260728-root-cause-plan.md`  
- `lib/ai_recommend_model/avatar_generation/flux_config.py`  
- `lib/ai_recommend_model/avatar_generation/preprocessing/reference.py`  
- `lib/ai_recommend_model/avatar_generation/worker.py`  
- Microsoft MAI-Image-2.5 Model Card (2026-06-02)

---

## 11. 분석 메타

- 방법: 저장소 read-only 추적 + 기존 staging forensic 문서 교차 + MAI 공개 스펙  
- 코드 수정: **없음**  
- 실행/배포/생성: **없음**  
- 본 문서 목적: 의사결정용 총괄 기록  
