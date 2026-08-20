# Fraud Check v2 Implementation Status

## 구현 완료

- `POST /v2/fraud/check` 및 ACP template/MVP source 계약
- schema version, request ID, source, mode, 객체 타입, label leakage 검증
- inbound `FRAUD_CHECK_API_KEY` Bearer 인증
- Claims Context/Document Gateway와 `CLAIMS_INTERNAL_API_KEY` 인증
- document ID 전용 PDF 다운로드, MIME/크기/SHA-256 검증
- PDF text 추출과 안전한 parser fallback, OCR/VLM provider interface
- claim/PDF 금액·날짜·병원·영수증 ID 비교
- receipt ID/hash, binary/text/perceptual fingerprint 중복 분석
- 피보험자·병원 반복 및 병원 과다 청구 분석
- 복합 신호, risk score, reason code, evidence
- fraud 및 핵심 장애의 human review 불변식
- v1 호환 API 유지
- unit/API handler/evaluation 테스트

## 운영 구성 시 필요한 항목

- OCR provider: scan-only 실문서 처리를 위해 조직 표준 OCR 구현을 `OcrProvider`에 주입
- VLM provider: OCR 결과가 불충분한 경우 승인된 모델 구현을 `VlmProvider`에 주입
- secret manager에서 두 API key 공급
- 운영 threshold calibration 및 지속적인 drift/precision/recall 관측

provider가 없는 상태에서 text layer가 없는 문서는 정상 판정하지 않고 human review 처리한다.

## 검증 결과

- Fraud Check unittest: 14/14 통과
- ACP v2 remote plugin 계약 테스트: 10/10 통과
- ACP generated eval 23건: precision 1.0, recall 1.0, F1 1.0
- human review routing invariant violation: 0
- 실제 HTTP smoke: ACP Context/PDF API -> Fraud Check v2 분석 성공

합성 eval 결과는 기능 계약 확인용이며 운영 성능을 보증하지 않는다.
