# Fraud Check Agent

`Automated_Claims_Processing`와 실제 계약으로 연결되는 독립 사기탐지 서비스입니다.
v1 호환 계약과 원시 문서 증거를 분석하는 v2 계약을 함께 지원합니다.

## 안전 원칙

- 사기 의심은 자동 거절 사유가 아니라 `human_review` 라우팅 사유입니다.
- Claims Context 핵심 조회 장애는 v2 `status: failed`와 `human_review`로 fail-closed 처리합니다.
- 원격 플러그인은 장애 시 `failure_policy: human_review` 계약을 지킵니다.
- 정답 라벨이나 평가 데이터는 런타임 입력으로 사용하지 않습니다.

## 구성

```text
Automated_Claims_Processing
  -> POST Fraud_Check /v2/fraud/check
  <- fraud signal + risk score + evidence

Fraud_Check
  -> GET Claims /internal/v1/fraud-context/claims/{claim_id}
  -> GET Claims /internal/v1/claims/{claim_id}/documents
  -> GET Claims /internal/v1/documents/{document_id}/content
```

v2에서는 Fraud Check가 Claims 심사 API나 결제/거절 API를 호출하지 않습니다.

## 실행

PowerShell 두 개를 열어 먼저 상대 프로젝트를 실행합니다.

```powershell
cd C:\Users\PC\AA\Automated_Claims_Processing
python -m uvicorn mvp.app.main:app --port 8000
```

그다음 이 서비스를 실행합니다.

```powershell
cd C:\Users\PC\AA\Fraud_Check
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8020
```

확인 URL:

- `http://127.0.0.1:8020/health`
- `http://127.0.0.1:8020/ready`
- `http://127.0.0.1:8020/docs`

## API

### `POST /v1/fraud/check`

상대 프로젝트의 tool payload를 직접 받습니다.

```json
{
  "claim": {"receipt_id": "RCT-1", "receipt_hash": "HASH-1", "provider_id": "P-1"},
  "claim_history": {
    "prior_receipt_ids": [],
    "prior_receipt_hashes": ["HASH-1"],
    "same_insured_provider_claims_30d": 0,
    "same_provider_claims_30d": 0
  },
  "signals": {},
  "insured_profile": {"insured_id": "INS-1"}
}
```

### `POST /v1/agent/process`

전체 claim schema를 `{"claim": {...}}` 형태로 보내면 독립 사기탐지와 상대 프로젝트의
`POST /reviews`를 실행하고 최종 라우팅을 합칩니다.

이 경로는 v1 prototype 호환용입니다. 신규 연동은 `/v2/fraud/check`를 사용합니다.

### `POST /v2/fraud/check`

ACP의 template/MVP v2 plugin이 전송하는 `schema_version: 2.0.0` 계약을 받습니다. 요청 schema는
`ai_agent_template/schemas/fraud_check_v2_request.schema.json`, 응답 schema는
`ai_agent_template/schemas/fraud_check_v2_response.schema.json`입니다.

분석 항목은 다음과 같습니다.

- 영수증 ID/hash, PDF SHA-256, text/perceptual fingerprint 중복
- PDF에서 추출한 금액·병원·영수증 ID·진료일과 claim 비교
- 동일 피보험자/병원 30일 반복 및 병원 30일 과다 청구
- 복수 신호 결합, risk score, reason code, evidence
- 문서 누락·손상·판독 실패 및 Context 장애의 human review 처리

PDF text layer를 우선 사용하며 OCR/VLM은 `DocumentPipeline`의 provider 인터페이스로 주입합니다.
provider가 구성되지 않았는데 text layer가 없으면 정상으로 간주하지 않고 human review로 보냅니다.

## 상대 프로젝트에 플러그인 연결

ACP에는 v2 remote plugin과 Claims 내부 API가 구현되어 있습니다. 양쪽에 같은 값을 설정합니다.

```text
FRAUD_CHECK_API_KEY=<ACP가 Fraud Check를 호출할 때 쓰는 키>
CLAIMS_INTERNAL_API_KEY=<Fraud Check가 ACP 내부 API를 호출할 때 쓰는 키>
CLAIMS_INTERNAL_BASE_URL=http://127.0.0.1:8000
```

Fraud Check와 ACP를 같은 포트에 실행할 수 없으므로 실제 배치에서는 Fraud Check 포트를 별도로
지정하십시오. 예: ACP `8000`, Fraud Check `8020`.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ACP가 생성한 독립 eval split을 실제 PDF 바이트로 평가합니다. 정답 label은 inference 요청에
포함하지 않고 metric 계산 단계에서만 사용합니다.

```powershell
python scripts/evaluate_acp_generated.py C:\Users\PC\AA\Automated_Claims_Processing\data_generator\generated
```
