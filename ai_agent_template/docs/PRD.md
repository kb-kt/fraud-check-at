# Product Requirements Document: Fraud Check AI Agent Template

## 1. 문서 목적

이 문서는 보험 청구 Fraud Check AI Agent를 일관되게 개발·평가·운영하기 위한 `ai_agent_template`의 제품 요구사항을 정의한다.

`ai_agent_template`은 실행 서비스 자체가 아니라 다음 산출물의 단일 기준이다.

- 입력·출력 JSON 계약
- Fraud 탐지 workflow
- Tool과 Plugin 계약
- 표준 reason code와 안전 정책
- 평가 지표와 합격 기준
- SDK와 Starter Kit 요구사항
- Template을 기반으로 만드는 Fraud_Check MVP의 구현 기준

Fraud_Check의 연동 대상은 `Automated_Claims_Processing`의 다음 두 실행 형태다.

1. `ai_agent_template/developer_kit/starter_kit` 기반 애플리케이션
2. `/mvp` 애플리케이션

두 연동 대상은 동일한 Fraud_Check 호출 계약을 사용해야 하며, Fraud_Check 내부 workflow는 호출자가 어느 구현인지에 의존하지 않아야 한다.

## 2. 배경

`Automated_Claims_Processing`는 claim을 접수하고 보험금 심사 workflow를 수행한다. 해당 workflow의 `fraud_signal_checker` 단계는 외부 Fraud_Check Agent를 호출할 수 있다.

목표 흐름은 다음과 같다.

```text
Automated_Claims_Processing
  -> claim 접수 및 저장
  -> Fraud_Check 분석 요청
  -> Fraud_Check가 문서·과거 이력·집계 증거 분석
  -> fraud signal 반환
  -> Automated_Claims_Processing가 fraud signal을 포함하여 심사 계속
```

Fraud_Check는 보험금 지급 또는 부지급을 결정하지 않는다. Fraud 의심 여부, 근거, 위험 점수와 사람 심사 필요 여부만 반환한다. 최종 보험 심사는 `Automated_Claims_Processing`와 사람 심사자가 담당한다.

현재 Fraud_Check에는 단순 규칙 기반 prototype이 존재하지만 다음 기능은 아직 Template로 표준화되지 않았다.

- 실제 PDF 및 문서 메타데이터 분석
- 과거 청구와 문서 조회
- 의료기관·피보험자 집계 검증
- Tool별 증거와 실패 기록
- 평가 라벨 기반 정식 evaluation harness
- Template 기반 MVP 생성

## 3. 제품 정의

### 3.1 Fraud Check AI Agent Template

Template은 다음을 제공한다.

- Fraud 분석 입력과 출력 schema
- 결정론적 탐지 Tool contract
- Plugin Interface
- workflow 정의
- 표준 reason code registry
- prompt 및 설명 생성 경계
- 평가 기준
- SDK와 Starter Kit

### 3.2 Fraud Check MVP

MVP는 Template을 로드하여 실제로 실행되는 애플리케이션이다.

- FastAPI 기반 Fraud Check API
- Claims context 및 문서 API client
- PDF·문서 분석 도구
- 과거 청구·집계 분석 도구
- SQLite 기반 분석 결과, Tool 호출, 감사 로그 저장
- 평가 실행 및 리포트 생성
- 운영 상태 확인 API

Template이 Agent의 계약과 정책을 정의하고, MVP가 실제 도구와 저장소를 연결한다. MVP가 Template에 없는 독자적인 Fraud 판단 규칙을 추가해서는 안 된다.

## 4. 목표

### 4.1 핵심 목표

- 합성 청구 데이터와 PDF를 사용해 재현 가능한 Fraud Check Agent를 개발한다.
- 중복 영수증, 위조·부정 문서, 반복 청구, 의료기관 과다 청구를 탐지한다.
- 모든 판단에 구조화된 reason code와 증거를 제공한다.
- Fraud 의심 또는 핵심 Tool 실패를 `human_review`로 안전하게 라우팅한다.
- `Automated_Claims_Processing`의 Template Starter Kit과 MVP 양쪽에서 동일하게 호출할 수 있다.
- 평가 라벨을 runtime으로부터 완전히 분리한다.
- 합성 구현을 실제 보험사 API와 저장소 Plugin으로 교체 가능한 구조를 제공한다.

### 4.2 비목표

- 보험 사기를 법적으로 확정하는 것
- 보험금 지급·일부 지급·부지급을 결정하는 것
- Fraud 의심만으로 자동 거절하는 것
- LLM의 자유 추론만으로 Fraud 여부를 판단하는 것
- 실제 개인정보나 실제 의료문서를 초기 MVP에서 사용하는 것
- `Automated_Claims_Processing`의 심사 workflow를 Fraud_Check가 대신 실행하는 것
- Fraud_Check가 Claims `/reviews` API를 역호출하는 것

## 5. 사용자와 시스템 행위자

- `Automated_Claims_Processing ai_agent_template` 개발자
- `Automated_Claims_Processing MVP` 개발자
- Fraud_Check Agent 개발자
- Fraud 탐지 규칙·모델 개발자
- 보험 보상 심사자 및 조사 담당자
- QA·평가 담당자
- 운영·보안·감사 담당자

## 6. 연동 경계

### 6.1 호출자

Fraud_Check를 호출할 수 있는 시스템은 다음과 같다.

```text
Automated_Claims_Processing/ai_agent_template/developer_kit/starter_kit
Automated_Claims_Processing/mvp
```

호출자는 기존 `fraud_signal_checker` Tool 단계에서 Fraud_Check를 호출한다.

### 6.2 Fraud_Check 책임

- 요청 schema 검증
- 필요한 Claims context와 문서 조회
- 문서 무결성·필드·중복 분석
- 과거 청구와 집계 분석
- 표준 reason code 생성
- 위험 점수 계산
- `human_review` 라우팅 결정
- Tool 근거와 실패 정보 기록
- schema-valid 응답 반환

### 6.3 Automated_Claims_Processing 책임

- claim 접수와 원본 보관
- claim과 document 연결
- 과거 claim, 문서 및 집계 데이터 제공
- Fraud_Check 호출 인증
- Fraud_Check 결과를 기존 심사 workflow에 반영
- Fraud 의심 또는 Fraud_Check 실패 시 사람 심사 강제
- 최종 심사 의견 및 보험금 지급 관련 처리

## 7. 지원해야 하는 탐지 항목

### FR-001 중복 영수증

다음 증거를 지원해야 한다.

- `receipt_hash`가 과거 영수증 hash와 일치
- legacy `receipt_id`가 과거 ID에 존재
- 문서 `content_hash`가 과거 문서와 일치
- SHA-256은 다르지만 정규화 텍스트 또는 이미지 유사도가 높은 수정 문서

표준 reason code:

```text
DUPLICATE_RECEIPT_SUSPECTED
ALTERED_DUPLICATE_DOCUMENT_SUSPECTED
```

### FR-002 위조·부정 문서

문서에서 추출한 값과 claim을 비교한다.

- 청구 금액 불일치
- 진료일·발급일 불일치
- 의료기관 불일치
- 영수증·문서 식별자 불일치
- 문서 손상, 읽기 실패 또는 신뢰도 부족
- 신뢰할 수 있는 upstream 문서 위조 신호

표준 reason code:

```text
DOCUMENT_AMOUNT_MISMATCH
DOCUMENT_DATE_MISMATCH
DOCUMENT_PROVIDER_MISMATCH
DOCUMENT_IDENTITY_MISMATCH
FRAUD_SIGNAL
```

문서 누락·손상·읽기 실패는 Fraud 확정 신호가 아니라 사람 심사 신호로 구분한다.

```text
DOCUMENT_MISSING
DOCUMENT_CORRUPTED
DOCUMENT_UNREADABLE
DOCUMENT_EXTRACTION_LOW_CONFIDENCE
```

### FR-003 동일 피보험자·동일 의료기관 반복 청구

초기 합성 데이터 기준은 다음과 같다.

```text
same_insured_provider_claims_30d >= 3
AND insured_id exists
```

표준 reason code:

```text
SAME_INSURED_PROVIDER_REPEAT_SUSPECTED
```

임계값은 설정과 버전으로 관리하고 코드에 분산해 하드코딩하지 않는다.

### FR-004 동일 의료기관 과다 청구 패턴

초기 합성 데이터 기준은 다음과 같다.

```text
same_provider_claims_30d >= 50
AND provider_id exists
```

표준 reason code:

```text
PROVIDER_PATTERN_ANOMALY_SUSPECTED
```

향후 의료기관 유형·규모·고유 피보험자 수·증가율 등으로 기준을 확장할 수 있어야 한다.

### FR-005 복합 Fraud

여러 신호가 동시에 존재하면 모든 독립 reason code와 증거를 보존한다. 위험 점수는 중복 근거를 과대 계산하지 않아야 한다.

### FR-006 Hard Negative

다음을 정상 또는 사람 확인 사례로 구분할 수 있어야 한다.

- 임계값 직전 반복 청구
- 규모가 큰 정상 의료기관
- 동일 금액이지만 서로 다른 영수증
- 정상적인 정기 진료
- 재생성되어 hash가 다르지만 claim과 일치하는 정상 PDF

## 8. 데이터 요구사항

### 8.1 Runtime 입력 데이터

초기 개발과 MVP는 `Automated_Claims_Processing/data_generator/generated`의 다음 산출물을 사용한다.

```text
claims_dev.jsonl
claims_eval.jsonl
historical_claims.jsonl
insureds.json
providers.json
document_metadata_dev.jsonl
document_metadata_eval.jsonl
claim_document_links_dev.jsonl
claim_document_links_eval.jsonl
fraud_context_seed_dev.jsonl
fraud_context_seed_eval.jsonl
documents/dev/{claim_id}/*.pdf
documents/eval/{claim_id}/*.pdf
```

### 8.2 평가 전용 데이터

```text
fraud_labels_dev.jsonl
fraud_labels_eval.jsonl
```

Fraud_Check runtime, Tool, prompt, retrieval index 및 API는 `fraud_labels_*`에 접근해서는 안 된다. Evaluation harness만 Agent 실행이 종료된 후 라벨을 읽을 수 있다.

### 8.3 데이터 최소화

초기 입력은 합성 token과 hash를 사용한다.

- `insured_id`
- `provider_id`
- `receipt_id`
- `receipt_hash`
- `document_id`
- `content_hash`

실제 이름, 주민등록번호, 전화번호, 주소, 계좌번호는 Agent 입력 계약에 포함하지 않는다.

### 8.4 원시 증거와 upstream signal 분리

`signals.suspected_duplicate_receipt`, `signals.fraudulent_document`, `signals.document_claim_mismatch`는 신뢰 가능한 외부 탐지기의 결과일 수 있다. 하지만 Fraud_Check 자체 평가에서는 정답 누출이 될 수 있으므로 다음 원칙을 적용한다.

- 원시 증거 평가 모드에서는 해당 값을 정답으로 간주하지 않는다.
- upstream signal을 사용했다면 출력 evidence에 출처를 표시한다.
- 원시 문서·이력 기반 결과와 upstream signal 기반 결과를 구분한다.
- 평가 리포트는 `raw_evidence`와 `upstream_signal_assisted` 모드를 분리한다.

## 9. API 호환 요구사항

### 9.1 v1 호환 경로

기존 Claims 원격 플러그인을 위해 다음 API를 유지한다.

```text
POST /v1/fraud/check
```

필수 응답 필드:

```json
{
  "fraud_suspected": false,
  "fraud_reason_codes": [],
  "risk_score": 0,
  "routing": "continue_claim_review",
  "engine_version": "1.0.0"
}
```

### 9.2 원시 증거 분석 경로

문서·이력 조회를 포함하는 정식 Template/MVP 계약은 versioned API로 제공한다.

```text
POST /v2/fraud/check
```

v2 응답은 v1 필드를 모두 포함하고 상세 문서·이력 근거와 경고를 추가한다.

### 9.3 호출자 독립성

`source_system`은 Claims Template Starter Kit 또는 MVP를 구분할 수 있지만, Fraud 판단 규칙을 바꾸는 용도로 사용해서는 안 된다. 호출자별 차이는 인증, base URL 및 adapter 설정에만 한정한다.

## 10. 안전 요구사항

### SAFE-001 자동 거절 금지

Fraud_Check는 자동 거절 또는 지급 결정을 반환하지 않는다.

### SAFE-002 Fraud 의심 라우팅

```text
fraud_suspected=true
-> requires_human_review=true
-> routing=human_review
```

### SAFE-003 Fail-closed

다음 실패는 `human_review`로 라우팅한다.

- Claims context 조회 실패
- 문서 조회 실패
- 핵심 문서 파싱 실패
- 과거 이력 조회 실패
- 필수 Tool timeout
- 출력 schema 검증 실패
- 증거 간 충돌

실패를 정상 또는 Fraud 없음으로 변환해서는 안 된다.

### SAFE-004 결정론적 판단

다음 항목은 LLM이 변경할 수 없다.

- hash 일치 여부
- 날짜·금액·기관 필드 비교
- 청구 이력 집계
- 위험 점수
- `fraud_suspected`
- `routing`
- reason code

LLM은 reviewer-facing 설명 생성만 보조할 수 있다.

### SAFE-005 설명과 증거

모든 Fraud reason code는 최소 하나의 구조화된 evidence 또는 Tool 결과를 참조해야 한다.

## 11. 비기능 요구사항

### NFR-001 스키마 안정성

- JSON Schema Draft 2020-12를 사용한다.
- schema에 version을 명시한다.
- breaking change는 major version으로 관리한다.

### NFR-002 가용성과 장애 격리

- Claims Template 또는 MVP 장애를 구분 가능한 오류로 반환한다.
- Fraud_Check 장애가 Claims 자동 지급·거절로 이어지지 않아야 한다.
- retryable 오류와 non-retryable 오류를 구분한다.

### NFR-003 성능

- v1 feature-only 경로는 기존 3초 timeout 내 처리를 목표로 한다.
- v2 문서 분석 timeout은 설정 가능해야 하며 Claims caller와 동일한 값으로 조정한다.
- Tool별 duration과 전체 latency를 기록한다.

### NFR-004 보안

- 서비스 간 인증을 환경변수 또는 secret provider에서 로드한다.
- 요청이 제공한 임의 URL을 그대로 호출하지 않는다.
- 허용된 Claims base URL과 document reference만 사용한다.
- 로그에 원문 문서, 전체 claim, 인증정보를 기록하지 않는다.

### NFR-005 감사 가능성

다음을 추적할 수 있어야 한다.

- request ID와 claim ID의 tokenized 값
- engine, schema, workflow, rule version
- Tool 상태, duration, error code
- reason code와 evidence reference
- 최종 routing

### NFR-006 재현성

동일한 입력, Template 버전, Plugin 버전, 설정으로 실행하면 결정론적 결과가 동일해야 한다.

## 12. 평가 요구사항

필수 평가 지표:

- `schema_validity`
- `fraud_precision`
- `fraud_recall`
- `false_positive_rate`
- `false_negative_rate`
- `reason_code_exact_match`
- `document_field_accuracy`
- `duplicate_detection_recall`
- `human_review_recall`
- `tool_failure_safe_route_rate`
- 시나리오별 정확도와 latency

합성 결정론적 시나리오의 MVP 목표:

```text
schema_validity = 100%
fraud_recall = 100% for deterministic scenarios
hard_negative_false_positive_rate = 0%
human_review_recall = 100%
tool_failure_safe_route_rate = 100%
automatic_denial_count = 0
label_leakage_count = 0
```

실제 이미지 OCR 또는 model 기반 탐지는 별도 threshold와 confidence calibration을 정의한다.

## 13. Template 산출물

```text
ai_agent_template/
  config/
  docs/
    PRD.md
    TECH_SPEC.md
    CONFIGURATION.md
    API_SPEC.md
    EVALUATION.md
    OPERATIONS.md
  schemas/
  workflows/
  tools/contracts/
  standards/
  prompts/
  examples/
  eval/
  db/
  developer_kit/
    sdk/
    plugin_interface/
    plugins/synthetic/
    starter_kit/
```

## 14. 개발 단계

1. PRD와 TECH_SPEC 승인
2. v1/v2 입력·출력 schema 확정
3. reason code와 evidence 표준 확정
4. Tool contract와 workflow 정의
5. SDK와 synthetic Plugin 구현
6. Data Generator dev 데이터 기반 evaluation
7. Claims context·document API Plugin 구현
8. Starter Kit smoke test
9. Template 기반 `/mvp` 생성
10. Claims Template Starter Kit 및 MVP와 종단간 검증

## 15. 인수 기준

Template 요구사항 완료 조건:

- Fraud_Check 역할과 Claims 역할이 분리되어 있다.
- Claims Template Starter Kit과 MVP가 같은 호출 계약을 사용한다.
- v1 호환과 v2 원시증거 분석 경로가 정의되어 있다.
- 입력·출력·evidence·Tool schema가 정의되어 있다.
- 최소 4개 핵심 탐지 항목의 workflow와 reason code가 정의되어 있다.
- Tool 실패와 Fraud 의심은 모두 안전하게 `human_review`로 라우팅된다.
- 평가 라벨 격리와 평가 지표가 정의되어 있다.
- SDK, Plugin Interface, Starter Kit 및 MVP 경계가 명확하다.
- Fraud_Check가 Claims `/reviews`를 역호출하지 않는다.

## 16. 리스크와 대응

### 리스크 1: 사전 signal이 정답처럼 사용됨

대응: 원시 증거 모드와 upstream-assisted 모드를 분리하고 평가 결과도 별도로 산출한다.

### 리스크 2: 합성 PDF가 실제 문서 분석 난이도를 반영하지 못함

대응: 텍스트 PDF, 실제 이미지형 PDF, 손상·암호화·저품질 문서를 단계적으로 추가하고 시나리오별 결과를 분리한다.

### 리스크 3: 3초 timeout 안에 다중 PDF 분석 불가

대응: v1 빠른 경로와 v2 문서 분석 경로를 분리하고 timeout을 호출자와 함께 설정한다. 향후 비동기 분석을 확장 가능하게 한다.

### 리스크 4: Claims 구현에 강결합

대응: `ClaimsGateway` Plugin 계약을 두고 Template Starter Kit과 MVP adapter가 동일한 context DTO를 반환하게 한다.

### 리스크 5: Fraud 의심을 자동 부지급으로 오용

대응: 출력 schema에 지급 결정을 포함하지 않고 `routing=human_review`만 허용한다.

