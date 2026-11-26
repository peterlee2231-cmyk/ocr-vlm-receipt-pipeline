# 파이프라인 아키텍처

## 데이터 흐름

```
data/receipts/*.png (파일명 순)
  → extract_raw_text  (src/app.py:34)   VLM 원문 전사
  → extract_fields    (src/app.py:56)   줄 단위 구조화 → 경비 레코드
  → 손상 파일 건너뛰기 / receipt_key 중복 제외  (src/app.py:91)
  → output/index.json (경비 KB) + 리포트 {loaded, skipped, errors}
  → answer            (src/app.py:148)  KB 조회 결과를 근거로 자연어 답변
```

## 함수별 설계

### extract_raw_text (src/app.py:34)

- `llm.extract_text(image_path, instruction)`에 이미지와 전사 지시문(src/app.py:24)을 그대로 전달한다.
- 지시문의 5요건: 위→아래 순서 읽기 / 요약·해석 금지 / 상호명·날짜·품목·금액 누락 금지 / 그대로 전사 / 표 행 유지.
- VLM 응답은 앞뒤 공백·개행만 `strip()`하고 본문은 가공하지 않는다 — 구조화는 다음 단계의 책임이다.

### extract_fields (src/app.py:56)

- 빈 줄을 제외한 줄 리스트로 정규화한 뒤 위치 기준으로 구분한다:
  - 첫 줄 → 상호명, 둘째 줄 → 결제 날짜
  - 중간 줄 → 품목(이름 + 금액), 마지막 줄 → 합계·총액
- 금액 파싱: `^(.+?)\s+([\d,]+)$`로 품목명/금액을 분리하고, 쉼표 제거 후 int 변환(_parse_amount, src/app.py:51).
- 합계 줄은 품목 목록(items)에 넣지 않고 `total`로 저장한다.
- `category`는 완성본인 categorize()(src/app.py:43)가 상호명 키워드로 분류한다: 카페→식비, 택시→교통비, 호텔→숙박비, 그 외 기타.
- `receipt_key = "상호명|날짜|총액"` — 중복 판정의 단일 기준.
- 줄 수가 3개 미만이거나 품목/합계 줄을 해석할 수 없으면 ValueError — 판독 내용을 임의로 채우지 않는다.

### ingest_all (src/app.py:91)

- `data/receipts` 최상위 `*.png`만 파일명 순으로 스캔한다. `lowquality/` 하위 폴더는 스캔 대상에서 제외한다.
- 파일별 try/except: 한 파일의 오류가 전체 적재를 중단시키지 않는다. 실패 시 `읽기 실패 {파일}: {사유}`를 errors에 기록하고 다음 파일로 진행한다.
- receipt_key가 이미 처리한 key와 같으면 `중복 영수증 {파일}`을 errors에 기록하고 KB에 재저장하지 않는다.
- 레코드에 `file` 식별자(확장자 제외 파일명)를 추가하고, `output/index.json`에 UTF-8(`ensure_ascii=False`, `indent=2`)로 저장한다.
- 리포트: `{loaded, skipped, errors}` — skipped는 건너뛴(손상+중복) 건수. 질의 기능의 `_ensure_ingested`(src/app.py:124)와 같은 키 체계를 공유한다.

### answer (src/app.py:148)

- 첫 질의 전 `_ensure_ingested()`로 KB가 비어 있으면 적재를 먼저 수행한다(프로세스당 1회).
- 질문 문자열에 레코드의 merchant가 포함되면 해당 레코드를 context로 사용하고, 아니면 `{적재_건수, 건너뛴_건수}` 요약을 context로 사용한다.
- `llm.complete()`(src/llm.py:148)이 조회 결과 JSON만 근거로 한국어 한 문장 답변을 생성한다.
- 반환: `{answer, sources(["kb:{file}"]), metrics}`.

## 처리 순서 특이점

파일명 정렬에서 `receipt-cafe-01-rescan.png`가 `receipt-cafe-01.png`보다 앞선다(`-` < `.`). 그 결과 재스캔본이 먼저 적재되고, 원본 파일명이 `중복 영수증 receipt-cafe-01.png`으로 errors에 기록된다. 이는 실습 지시 예시 출력과 일치하는 의도된 동작이다.

## 검증 결과 (2026-11-26)

- `python3 src/app.py` → loaded 3, skipped 2
  - errors: `읽기 실패 receipt-broken.png: 이미지 파일을 읽을 수 없습니다 (손상됨)`, `중복 영수증 receipt-cafe-01.png`
- 질의 4건 모두 정답 + `kb:` 출처 표기:
  - 오로라카페 강남점 → 10,000원 / 모범택시 → 18,700원
  - 오로라호텔 서울 → 객실료 150,000·조식 20,000·세금 17,000 = 187,000원
  - 적재 건수 질의 → 3건
