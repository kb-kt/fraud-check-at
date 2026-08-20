# Technical Specification: Fraud Check AI Agent Template

## 1. 목적과 범위

이 문서는 `PRD.md`를 구현하기 위한 Fraud Check AI Agent Template의 기술 구조, schema, workflow, Tool/Plugin 계약, API, 저장소, 평가 및 통합 방식을 정의한다.

구현 대상은 다음 두 계층이다.

```text
ai_agent_template
  -> reusable contracts, SDK, plugins, workflow, starter kit

mvp
  -> ai_agent_template을 로드하는 실제 Fraud_Check 서비스
```

연동 대상은 다음 두 애플리케이션이다.

```text
Automated_Claims_Processing/ai_agent_template/developer_kit/starter_kit
Automated_Claims_Processing/mvp
```

## 2. 설계 원칙

1. Fraud 여부와 reason code는 결정론적 Tool 결과가 결정한다.
2. LLM은 구조화된 결과를 변경하지 않고 설명 생성만 보조한다.
3. 모든 Fraud 의심과 핵심 Tool 실패는 `human_review`로 fail-closed 처리한다.
4. Fraud_Check는 Claims 심사 API를 호출하지 않는다.
5. Claims 데이터는 직접 DB 연결이 아니라 `ClaimsGateway`를 통해 조회한다.
6. Template Starter Kit과 Claims MVP는 동일한 gateway DTO를 제공한다.
7. 정답 라벨은 evaluation process에서만 접근한다.
8. v1 기존 계약을 유지하고 원시증거 분석은 v2로 확장한다.

## 3. 전체 아키텍처

```text
Automated_Claims_Processing
  [Template Starter Kit or MVP]
        |
        | POST /v1 or /v2/fraud/check
        v
Fraud_Check API
        |
        v
Fraud WorkflowRunner
  -> validate_input
  -> load_fraud_context
  -> fetch_documents
  -> inspect_documents
  -> compare_document_and_claim
  -> check_duplicate_receipt
  -> check_claim_history
  -> check_provider_pattern
  -> calculate_fraud_score
  -> apply_safety_policy
  -> generate_explanation(optional)
  -> validate_output
        |
        v
Fraud result + evidence + routing
        |
        v
Automated_Claims_Processing continues claim review
```

Fraud_Check가 문서나 이력을 추가 조회할 때는 다음 경계를 사용한다.

```text
Fraud Workflow
  -> ClaimsGateway Protocol
      -> TemplateStarterKitClaimsGateway
      -> MvpClaimsGateway
      -> SyntheticFileClaimsGateway for tests
```

## 4. 권장 저장소 구조

```text
Fraud_Check/
  ai_agent_template/
    __init__.py
    config/
      app_config.yaml
      model_config.yaml
      plugins.yaml
    docs/
    schemas/
      fraud_check_input.schema.json
      fraud_check_output.schema.json
      fraud_evidence.schema.json
      document_analysis_result.schema.json
      fraud_context.schema.json
      evaluation_result.schema.json
      api_error.schema.json
      tool_contracts.schema.json
    workflows/
      fraud_check_workflow.yaml
      human_review_rules.yaml
    tools/contracts/
    standards/
      reason_codes.yaml
      evidence_codes.yaml
      routing_codes.yaml
      document_codes.yaml
    prompts/
      system_prompt.md
      fraud_explanation_prompt.md
      output_format_prompt.md
      human_review_policy_prompt.md
    examples/
    eval/
    db/
      schema.sql
      migrations/
    developer_kit/
      sdk/fraud_agent_sdk/
      plugin_interface/
      plugins/synthetic/
      starter_kit/
  mvp/
    app/
    config/
    tests/
    runtime/
```

## 5. 계약 버전 전략

### 5.1 v1 compatibility

현재 Claims 원격 Plugin이 사용하는 계약이다.

```text
POST /v1/fraud/check
timeout target: 3000ms
mode: feature_only or inline_context
```

v1은 다음 입력을 지원한다.

```json
{
  "claim": {},
  "claim_history": {},
  "signals": {},
  "insured_profile": {}
}
```

v1 응답:

```json
{
  "fraud_suspected": false,
  "fraud_reason_codes": [],
  "risk_score": 0,
  "routing": "continue_claim_review",
  "engine_version": "1.0.0"
}
```

### 5.2 v2 evidence-based contract

정식 문서·이력 분석 계약이다.

```text
POST /v2/fraud/check
mode: raw_evidence | upstream_signal_assisted
```

Breaking change는 v2 schema major version 안에서 허용하지 않는다. 신규 optional 필드는 minor version으로 추가한다.

## 6. v2 입력 DTO

권장 입력:

```json
{
  "schema_version": "2.0.0",
  "request_id": "REQ-SYN-000001",
  "claim_id": "CLM-EVAL-000001",
  "source_system": "automated_claims_processing_mvp",
  "analysis_mode": "raw_evidence",
  "claim": {
    "receipt_id": "RCT-SYN-000001",
    "receipt_hash": "HASH",
    "provider_id": "PROV-SYN-001",
    "claimed_amount": 180000,
    "claim_date": "2026-07-02",
    "treatment_start_date": "2026-07-01",
    "treatment_end_date": "2026-07-01",
    "diagnosis_code": "SYN-M54",
    "treatment_code": "TRT-NONCOV-001"
  },
  "insured_profile": {
    "insured_id": "INS-SYN-001"
  },
  "document_refs": [
    {
      "document_id": "DOC-SYN-001",
      "document_type": "medical_receipt",
      "content_hash": "SHA256",
      "mime_type": "application/pdf"
    }
  ],
  "inline_context": {
    "claim_history": null,
    "document_metadata": []
  },
  "upstream_signals": {},
  "options": {
    "include_evidence": true,
    "include_tool_trace": false,
    "strict_schema": true
  }
}
```

### 6.1 필수 필드

- `schema_version`
- `request_id`
- `claim_id`
- `source_system`
- `analysis_mode`
- `claim`
- `insured_profile`

### 6.2 source_system

허용 초기 값:

```text
automated_claims_processing_template
automated_claims_processing_mvp
synthetic_test_harness
```

`source_system`은 adapter와 감사 식별에만 사용한다. 탐지 임계값을 호출자별로 변경해서는 안 된다.

### 6.3 context 조회 정책

- `inline_context`가 완전하면 해당 context를 schema 검증 후 사용할 수 있다.
- 부족한 context는 설정된 `ClaimsGateway`로 조회한다.
- API 요청이 임의의 `base_url` 또는 download URL을 지정하게 하지 않는다.
- `document_id`는 gateway가 허용된 Claims 서비스에서 해석한다.

## 7. v2 출력 DTO

```json
{
  "schema_version": "2.0.0",
  "request_id": "REQ-SYN-000001",
  "claim_id": "CLM-EVAL-000001",
  "status": "completed",
  "fraud_suspected": true,
  "fraud_reason_codes": [
    "DOCUMENT_AMOUNT_MISMATCH"
  ],
  "risk_score": 80,
  "routing": "human_review",
  "requires_human_review": true,
  "engine_version": "2.0.0",
  "workflow_version": "1.0.0",
  "document_findings": [
    {
      "document_id": "DOC-SYN-001",
      "finding_codes": ["DOCUMENT_AMOUNT_MISMATCH"],
      "confidence": 1.0,
      "evidence_ids": ["EVD-001"]
    }
  ],
  "history_findings": [],
  "evidence": [
    {
      "evidence_id": "EVD-001",
      "evidence_type": "field_comparison",
      "source": "medical_receipt",
      "field": "claimed_amount",
      "observed_value": "223100",
      "expected_value": "180000",
      "summary": "Document amount differs from claim amount"
    }
  ],
  "analysis_warnings": [],
  "tool_failures": [],
  "review_summary": "문서 금액과 청구 금액이 일치하지 않아 사람 심사가 필요합니다."
}
```

### 7.1 출력 불변식

```text
fraud_suspected=true -> routing=human_review
fraud_suspected=true -> requires_human_review=true
tool_failures contains critical failure -> routing=human_review
routing=continue_claim_review -> requires_human_review=false
risk_score is integer 0..100
every fraud_reason_code has evidence or trusted upstream signal reference
```

출력에는 `pay`, `partial_pay`, `deny`, 지급액과 같은 보험금 심사 결정을 포함하지 않는다.

## 8. ClaimsGateway 계약

### 8.1 Protocol

```python
class ClaimsGateway(Protocol):
    def get_fraud_context(self, claim_id: str) -> dict: ...
    def list_documents(self, claim_id: str) -> list[dict]: ...
    def get_document_content(self, document_id: str) -> bytes: ...
```

### 8.2 예상 Claims API

Template Starter Kit과 MVP는 가능하면 동일 경로를 제공한다.

```text
GET /internal/v1/fraud-context/claims/{claim_id}
GET /internal/v1/claims/{claim_id}/documents
GET /internal/v1/documents/{document_id}/content
```

API 경로가 다르면 adapter 내부에서만 변환한다. Fraud workflow에는 차이를 노출하지 않는다.

### 8.3 fraud context 응답 최소 필드

```json
{
  "claim_id": "CLM-EVAL-000001",
  "claim_history": {
    "prior_receipt_ids": [],
    "prior_receipt_hashes": [],
    "same_insured_provider_claims_30d": 0,
    "same_provider_claims_30d": 0,
    "same_diagnosis_claims_90d": 0,
    "manual_therapy_count_180d": 0
  },
  "document_metadata": []
}
```

## 9. Tool 계약

모든 Tool은 공통 envelope를 반환한다.

```json
{
  "tool_name": "string",
  "plugin_version": "string",
  "status": "success | failed",
  "result": {},
  "error": null,
  "duration_ms": 0,
  "metadata": {
    "contract_version": "1.0.0"
  }
}
```

### 9.1 `fraud_context_loader`

목적: ClaimsGateway 또는 inline context에서 과거 이력과 문서 참조를 로드한다.

실패 정책: `human_review`

### 9.2 `document_fetcher`

목적: 허용된 document ID로 PDF bytes를 가져오고 size, MIME, hash를 검증한다.

실패 정책: `human_review`

필수 보호:

- 최대 파일 크기
- 최대 문서 수
- 허용 MIME
- path traversal 차단
- redirect 정책
- timeout

### 9.3 `pdf_integrity_checker`

목적: PDF header, EOF, 암호화, page count, hash, 파싱 가능 여부를 확인한다.

문서 처리 실패는 Fraud 확정이 아니라 review warning을 생성한다.

### 9.4 `document_field_extractor`

목적: PDF text layer 또는 OCR에서 구조화 필드를 추출한다.

출력 필드:

- `receipt_id`
- `insured_id`
- `provider_id`
- `issue_date`
- `treatment_start_date`
- `treatment_end_date`
- `diagnosis_code`
- `treatment_code`
- `claimed_amount`
- 필드별 confidence와 source page

### 9.5 `document_claim_matcher`

목적: 추출 필드와 claim 필드를 결정론적으로 비교한다.

출력 reason code:

- `DOCUMENT_AMOUNT_MISMATCH`
- `DOCUMENT_DATE_MISMATCH`
- `DOCUMENT_PROVIDER_MISMATCH`
- `DOCUMENT_IDENTITY_MISMATCH`

### 9.6 `duplicate_receipt_checker`

목적:

- receipt hash exact match
- legacy receipt ID match
- document content hash exact match
- normalized text fingerprint similarity
- perceptual hash similarity

유사도 임계값과 알고리즘 버전을 metadata에 기록한다.

### 9.7 `claim_history_checker`

목적: 동일 피보험자·의료기관 반복 청구를 확인한다.

초기 규칙:

```text
same_insured_provider_claims_30d >= 3
```

### 9.8 `provider_pattern_checker`

목적: 의료기관 청구량 이상 패턴을 확인한다.

초기 규칙:

```text
same_provider_claims_30d >= 50
```

### 9.9 `fraud_score_calculator`

목적: 중복 evidence를 정규화하고 설정된 rule weight로 위험 점수를 계산한다.

점수는 설명 가능한 정수 0..100이어야 하며, 각 기여 항목을 출력한다.

### 9.10 `fraud_decision_validator`

목적: 최종 출력 schema와 안전 불변식을 검증한다.

실패 정책: 응답 성공으로 위장하지 않고 `human_review` 오류 응답 또는 안전 fallback을 생성한다.

## 10. Workflow

권장 `fraud_check_workflow.yaml`:

```yaml
version: 1.0.0
workflow_id: fraud_check_v1
input_schema: schemas/fraud_check_input.schema.json
output_schema: schemas/fraud_check_output.schema.json
steps:
  - id: validate_input
    type: schema_validation
    on_failure: fail
  - id: load_context
    type: tool
    tool: fraud_context_loader
    on_failure: human_review
  - id: fetch_documents
    type: tool
    tool: document_fetcher
    on_failure: human_review
  - id: inspect_pdf
    type: tool
    tool: pdf_integrity_checker
    on_failure: human_review
  - id: extract_fields
    type: tool
    tool: document_field_extractor
    on_failure: human_review
  - id: compare_document_claim
    type: tool
    tool: document_claim_matcher
    on_true: human_review
  - id: check_duplicate
    type: tool
    tool: duplicate_receipt_checker
    on_true: human_review
  - id: check_history
    type: tool
    tool: claim_history_checker
    on_true: human_review
  - id: check_provider
    type: tool
    tool: provider_pattern_checker
    on_true: human_review
  - id: calculate_score
    type: tool
    tool: fraud_score_calculator
    on_failure: human_review
  - id: generate_explanation
    type: model
    required: false
    on_failure: deterministic_summary
  - id: validate_output
    type: tool
    tool: fraud_decision_validator
    on_failure: fail_closed
```

모든 탐지 Tool을 실행해 복수 reason code를 보존한다. 첫 번째 Fraud 신호가 발견됐다고 이후 evidence 수집을 중단하지 않는다.

## 11. Reason code registry

초기 표준:

```text
DUPLICATE_RECEIPT_SUSPECTED
ALTERED_DUPLICATE_DOCUMENT_SUSPECTED
FRAUD_SIGNAL
DOCUMENT_AMOUNT_MISMATCH
DOCUMENT_DATE_MISMATCH
DOCUMENT_PROVIDER_MISMATCH
DOCUMENT_IDENTITY_MISMATCH
SAME_INSURED_PROVIDER_REPEAT_SUSPECTED
PROVIDER_PATTERN_ANOMALY_SUSPECTED
DOCUMENT_MISSING
DOCUMENT_CORRUPTED
DOCUMENT_UNREADABLE
DOCUMENT_EXTRACTION_LOW_CONFIDENCE
CONTEXT_UNAVAILABLE
TOOL_FAILURE
HUMAN_REVIEW_REQUIRED
```

Registry 항목은 다음 metadata를 가진다.

- code
- category
- description
- default_weight
- implies_fraud_suspected
- requires_human_review
- active_from_version

문서 처리 실패 코드는 `requires_human_review=true`지만 `implies_fraud_suspected=false`다.

## 12. 점수와 라우팅 정책

점수 정책은 `config` 또는 standards artifact에서 versioning한다.

초기 원칙:

- exact duplicate, 명확한 문서 필드 변조, 신뢰 가능한 fraud signal은 Fraud 의심으로 처리한다.
- 반복·기관 패턴 임계값 도달은 Fraud 의심으로 처리한다.
- 문서 누락·손상·저신뢰 추출은 Fraud 확정 없이 `human_review`로 처리한다.
- hard negative 경계값은 Fraud 의심으로 처리하지 않는다.
- score가 낮더라도 명시적 안전 규칙이 있으면 `human_review`를 유지한다.

LLM 출력은 score와 routing을 수정할 수 없다.

## 13. Plugin Interface

필수 Plugin Protocol:

- `ToolPlugin`
- `ClaimsGatewayPlugin`
- `DocumentExtractorPlugin`
- `ModelProviderPlugin`
- 선택적 `SimilarityModelPlugin`

Plugin은 다음 metadata를 제공한다.

```text
name
version
contract_name
contract_version
owner
timeout_ms
failure_policy
```

초기 synthetic Plugin은 `Automated_Claims_Processing/data_generator/generated`를 읽는 adapter를 제공한다. 운영 Plugin은 Claims 내부 API를 사용한다.

## 14. SDK

권장 Python SDK package:

```text
ai_agent_template/developer_kit/sdk/fraud_agent_sdk
```

주요 공개 객체:

- `TemplateBundle`
- `SchemaValidator`
- `StandardsRegistry`
- `WorkflowLoader`
- `WorkflowRunner`
- `ToolRegistry`
- `PluginLoader`
- `EvaluationRunner`
- `EvidenceVerifier`
- `LabelLeakageGuard`

SDK는 Template artifact를 단일 출처로 사용하고 독자적인 reason code 또는 임계값을 갖지 않는다.

## 15. API 사양

### 15.1 공통

```text
Content-Type: application/json
OpenAPI: 3.1
JSON Schema: Draft 2020-12
```

### 15.2 Endpoint

| Method | Path | 목적 |
|---|---|---|
| GET | `/health` | 프로세스 상태 |
| GET | `/ready` | Template, DB, Claims gateway 준비 상태 |
| POST | `/v1/fraud/check` | 기존 Claims Plugin 호환 |
| POST | `/v2/fraud/check` | 원시 증거 기반 Fraud 분석 |
| GET | `/v2/analyses/{claim_id}` | 최신 분석 결과 조회 |
| POST | `/v2/analyses/{claim_id}/rerun` | 분석 재실행 |
| GET | `/v2/analyses/{claim_id}/audit-logs` | 감사 로그 조회 |
| POST | `/v2/evaluations` | 평가 실행 |
| GET | `/v2/evaluations/{evaluation_id}` | 평가 결과 조회 |
| GET | `/v2/standards/reason-codes` | reason code registry 조회 |

### 15.3 Error envelope

```json
{
  "request_id": "REQ-SYN-000001",
  "status": "failed",
  "error": {
    "code": "CONTEXT_UNAVAILABLE",
    "message": "Fraud context could not be loaded",
    "retryable": true
  },
  "safe_routing": "human_review"
}
```

표준 오류 코드:

```text
VALIDATION_ERROR
SCHEMA_VERSION_UNSUPPORTED
UNAUTHORIZED_SOURCE
CONTEXT_UNAVAILABLE
DOCUMENT_NOT_FOUND
DOCUMENT_TOO_LARGE
DOCUMENT_TYPE_UNSUPPORTED
DOCUMENT_PARSE_FAILED
DOCUMENT_EXTRACTION_FAILED
TOOL_TIMEOUT
TOOL_CONTRACT_ERROR
OUTPUT_VALIDATION_FAILED
INTERNAL_ERROR
```

## 16. 인증과 보안

초기 로컬 환경은 optional bearer token을 지원한다. 운영 확장 시 mTLS 또는 workload identity를 적용할 수 있게 인증 계층을 분리한다.

환경변수 예:

```text
FRAUD_CHECK_API_KEY
CLAIMS_TEMPLATE_BASE_URL
CLAIMS_MVP_BASE_URL
CLAIMS_INTERNAL_API_KEY
FRAUD_CHECK_SOURCE_PROFILE
```

요구사항:

- secret을 config 파일이나 응답에 노출하지 않는다.
- 허용된 source system만 요청할 수 있다.
- Claims gateway base URL은 서버 설정에서만 결정한다.
- 문서 bytes와 전체 OCR text를 일반 로그에 기록하지 않는다.
- Tool audit payload는 최소화하거나 token/hash만 저장한다.

## 17. 저장소 설계

Repository Protocol:

```text
FraudAnalysisRepository
  -> SQLiteFraudAnalysisRepository
  -> PostgreSQLFraudAnalysisRepository later
```

초기 테이블:

```text
schema_migrations
fraud_analyses
fraud_findings
fraud_evidence
tool_call_logs
document_analysis_cache
audit_logs
evaluation_runs
```

저장 원칙:

- schema validation 성공 후 저장한다.
- 원문 PDF는 Claims 저장소에 유지하고 Fraud DB에 복제하지 않는다.
- document cache는 hash, 추출 결과, parser version 중심으로 저장한다.
- 평가 라벨은 운영 DB에 저장하지 않는다.

## 18. 문서 분석 구현 단계

### Stage A: structured metadata baseline

- Data Generator의 `structured_fields`, content hash, text fingerprint 사용
- 결정론적 field matcher와 이력 규칙 검증
- Template workflow와 평가 harness 우선 완성

### Stage B: text PDF extraction

- 실제 PDF text layer에서 필드 추출
- metadata의 structured field를 runtime 정답으로 사용하지 않음

### Stage C: image PDF/OCR

- 이미지 렌더링과 OCR Plugin 적용
- 필드별 confidence 기록
- 저신뢰 extraction은 `human_review`

### Stage D: altered document similarity

- 실제 perceptual hash와 normalized OCR fingerprint
- 과거 문서 index와 유사도 검색
- threshold calibration 및 hard-negative 평가

## 19. Evaluation harness

입력:

```text
claims_dev.jsonl or claims_eval.jsonl
runtime fraud context and documents
```

정답:

```text
fraud_labels_dev.jsonl or fraud_labels_eval.jsonl
```

실행 순서:

1. runtime dataset만 Agent에 전달
2. Agent 결과 저장
3. Agent 실행 종료 후 labels 로드
4. claim ID로 결과와 라벨 결합
5. binary, reason code, routing, Tool failure, latency 평가
6. 시나리오별 리포트 생성

평가 중 다음 문자열 또는 필드가 runtime 입력에 있으면 실패 처리한다.

```text
expected_*
fraud_labels
fraud_scenario
정답 fraud_reason_codes
```

upstream signal assisted 평가에서는 사용한 signal 출처를 별도 기록한다.

## 20. 테스트 전략

### 20.1 Template contract tests

- 모든 JSON/YAML parse
- schema Draft 2020-12
- workflow Tool reference 일치
- reason code registry 일치
- example schema validation

### 20.2 Plugin conformance

- 모든 Plugin metadata와 envelope 검증
- timeout과 failure policy 검증
- invalid output 차단

### 20.3 탐지 단위 테스트

- exact hash duplicate
- legacy receipt ID duplicate
- altered duplicate
- forged amount/date/provider
- repeat count 2/3
- provider count 49/50
- 복합 Fraud
- hard negative
- missing/corrupt/unreadable document

### 20.4 종단간 테스트

각 호출자에 대해 동일 테스트를 수행한다.

```text
Claims Template Starter Kit -> Fraud_Check -> Claims workflow
Claims MVP -> Fraud_Check -> Claims workflow
```

필수 장애 테스트:

- Fraud_Check down
- Claims context API down
- document API timeout
- HTTP 4xx/5xx
- invalid JSON
- schema mismatch
- auth failure
- Tool timeout

모든 핵심 장애는 자동 지급·거절 없이 `human_review`로 끝나야 한다.

## 21. 성능과 실행 모델

### 21.1 v1

- feature-only 요청
- p95 목표 1초 이하
- caller timeout 3초 유지

### 21.2 v2

- structured/text PDF MVP p95 목표 5초 이하
- OCR 사용 시 timeout을 별도로 설정하고 측정 결과에 따라 조정
- caller와 server timeout이 일치해야 함
- 문서 수와 전체 bytes에 상한을 둠

향후 OCR 또는 대형 문서 처리 시간이 길면 다음 비동기 API를 추가할 수 있다.

```text
POST /v2/fraud/analyses -> 202 analysis_id
GET /v2/fraud/analyses/{analysis_id}
```

초기 MVP는 동기 API를 우선 구현한다.

## 22. 기존 prototype migration

현재 `app/fraud_engine.py`, `app/main.py`, `app/orchestrator.py`는 prototype으로 취급한다.

Migration 원칙:

- 기존 `/v1/fraud/check`의 응답 호환성을 유지한다.
- 규칙과 reason code를 Template standards로 이동한다.
- `check_fraud` 로직을 WorkflowRunner와 Tool Plugin으로 분해한다.
- `app/orchestrator.py`의 Claims `/reviews` 역호출을 제거한다.
- `ClaimsClient.run_review`를 `ClaimsGateway` context/document 조회로 교체한다.
- Template Starter Kit이 안정화된 후 `/mvp`를 생성한다.
- migration 완료 전까지 prototype은 회귀 비교 기준으로 유지한다.

## 23. 구현 순서

### Phase 1: Contract Foundation

- schemas
- standards registries
- examples
- API spec
- configuration spec

### Phase 2: Template Runtime

- Template loader
- schema validator
- workflow loader/runner
- Tool registry
- Plugin loader
- deterministic synthetic tools

### Phase 3: Evidence Pipeline

- ClaimsGateway
- document fetcher
- PDF integrity
- field extraction
- field matcher
- duplicate and history tools

### Phase 4: Evaluation

- leakage guard
- evaluation runner
- scenario metrics
- baseline and regression report

### Phase 5: Starter Kit

- FastAPI
- SQLite repository
- audit/tool logs
- health/readiness
- local synthetic Claims gateway

### Phase 6: MVP

- Template 기반 `/mvp`
- Claims Template/MVP gateway config
- reviewer view
- evaluation API

### Phase 7: Integration Acceptance

- Claims Template Starter Kit E2E
- Claims MVP E2E
- 장애·timeout·보안·성능 테스트
- remote plugin activation guide

## 24. 완료 기준

- Template 필수 artifact가 모두 존재하고 contract test를 통과한다.
- v1 기존 Claims remote plugin test가 계속 통과한다.
- v2 schema와 API가 문서·이력 근거를 지원한다.
- synthetic Tool이 23개 Fraud 시나리오를 처리한다.
- 결정론적 Fraud 시나리오 recall 100%를 달성한다.
- hard negative false positive가 0건이다.
- 문서 처리 실패는 Fraud 확정 없이 `human_review`로 라우팅된다.
- Claims Template Starter Kit과 MVP 양쪽 E2E가 통과한다.
- Tool failure safe route rate가 100%다.
- 자동 거절 출력이 존재하지 않는다.
- runtime이 평가 라벨에 접근하지 않는다.
- MVP가 Template schema, workflow, standards를 직접 로드하며 복제 규칙을 갖지 않는다.
