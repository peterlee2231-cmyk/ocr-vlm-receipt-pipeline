# 실습 기록 — 출장 경비 영수증 OCR/VLM 파이프라인

- 실습 일자: 2026-11-26
- 저장소: https://github.com/peterlee2231-cmyk/ocr-vlm-receipt-pipeline
- 실습 노트(재사용 패턴·교훈): [wiki/Labs.md](../wiki/Labs.md)

## 실습 시나리오

오로라 모빌리티 경영지원팀의 업무 자동화 담당자로서, 임직원들이 이미지로 제출하는 카페·택시·호텔 영수증을 자동 처리한다. 담당자가 영수증을 한 장씩 확인해 상호명·날짜·품목·금액을 경비 시스템에 입력하던 작업을 VLM 파이프라인으로 자동화하는 것이 목표다. 실제 상황이 반영된 변수:

- 같은 영수증이 다른 파일명(rescan)으로 재업로드됨 — 중복
- 읽을 수 없는 손상 이미지 포함
- 호텔 청구서처럼 품목이 표로 정리된 영수증
- 판독이 불확실한 저품질 이미지(lowquality/)

처리 흐름:

```
영수증 이미지 → 원문 텍스트 추출 → 경비 정보 구조화 → 손상·중복 확인 → 경비 KB 적재
```

적재된 경비 KB를 질의하는 기능(`answer()`, `categorize()`)은 완성된 코드로 제공된다.

## 프로젝트 구성

```
project/
├── data/
│   └── receipts/
│       ├── receipt-cafe-01.png
│       ├── receipt-cafe-01-rescan.png
│       ├── receipt-taxi-01.png
│       ├── receipt-hotel-01.png
│       ├── receipt-broken.png
│       └── lowquality/
│           └── receipt-lowquality-01.png
├── output/                # index.json — 경비 KB (적재 결과)
├── src/
│   ├── app.py             # 이번 실습에서 구현한 파이프라인 본체
│   └── llm.py             # 완성본 (수정 금지) — VLM 원문 추출 + LLM 답변 생성
├── wiki/                  # 지식 위키 — Home.md가 인덱스
├── wiki.md                # 위키 단일 파일 번들 — 다른 클라우드 이식용
└── docs/                  # 실습 전체 기록 (이 문서)
```

- `src/llm.py`: `llm.extract_text()` — 영수증 이미지에서 텍스트 추출, `llm.complete()` — 경비 KB 조회 결과로 답변 생성
- `src/app.py`: 이번 실습에서 구현 — `extract_raw_text()`, `extract_fields()`, `ingest_all()`

## 환경 설정

프로젝트 루트의 `.env`에 API 연결 정보를 둔다 (커밋 제외):

```
API_KEY=직접 입력
BASE_URL=...
MODEL=...
```

- API 키는 Python 코드에 직접 작성하지 않는다 — 값은 `.env`에만 존재한다.
- `API_KEY`가 없으면 mock 모드로 동작해 오프라인에서도 파이프라인 검증이 가능하다 (정답 원문은 `data/receipts/_truth.json`에서 제공).

## 과제별 구현

### 1. 영수증 원문 추출 — extract_raw_text() (src/app.py:34)

- VLM에 전달할 지시문에 5요건을 포함:
  1. 영수증에 보이는 글자를 위에서 아래 순서로 읽기
  2. 내용을 요약하거나 해석하지 않기
  3. 상호명, 날짜, 품목명, 금액을 빠뜨리지 않기
  4. 이미지에 보이는 내용을 그대로 옮겨 적기
  5. 표 형태의 영수증도 각 행의 내용 유지하기
- 이미지 경로와 지시문을 `llm.extract_text()`에 전달한다.
- VLM이 반환한 텍스트는 앞뒤 공백·개행만 `strip()`으로 정리해 반환한다 — 본문은 가공하지 않는다.

추출 결과 형식 (카페 예시):

```
오로라카페 강남점
2026-06-10
아메리카노 4,500
카페라떼 5,500
합계 10,000
```

### 2. 경비 정보 구조화 — extract_fields() (src/app.py:56)

- `extract_raw_text()`를 호출해 원문을 가져온 뒤, 빈 줄을 제외하고 위치 기준으로 구분:

| 위치 | 의미 |
|---|---|
| 첫 번째 줄 | 상호명 |
| 두 번째 줄 | 결제 날짜 |
| 중간 줄 | 품목명과 금액 |
| 마지막 줄 | 합계와 총액 |

- 금액은 쉼표를 제거한 뒤 int로 변환한다 (`_parse_amount`, src/app.py:51).
- 합계 줄은 품목 목록(items)에 넣지 않고 `total`로 저장한다.
- `category`는 제공된 `categorize()`의 결과를 저장한다 (src/app.py:43).
- `receipt_key = "상호명|날짜|총액"` — 중복 영수증을 구분하는 기준.

반환 구조 (택시 예시):

```json
{
    "merchant": "모범택시",
    "date": "2026-06-11",
    "total": 18700,
    "category": "교통비",
    "items": [
        {"name": "이동요금", "amount": 18700}
    ],
    "receipt_key": "모범택시|2026-06-11|18700"
}
```

- 호텔 청구서처럼 품목이 표 형태로 나열된 경우에도 각 품목을 빠짐없이 items에 저장한다.

### 3. 손상된 영수증 처리

- 파일별 try/except로 한 이미지의 오류가 전체 적재 작업을 중단시키지 않게 한다.
- 손상된 영수증은 해당 파일만 건너뛰고 다음 영수증 처리를 계속한다.
- 건너뛴 파일의 이름과 오류 내용을 적재 결과의 errors에 기록한다: `읽기 실패 receipt-broken.png`
- 읽지 못한 영수증의 내용을 임의로 만들어 저장하지 않는다.

### 4. 중복 영수증 제외

- 파일 이름이 달라도 `receipt_key`가 같으면 동일한 영수증으로 판단한다.
- 이미 처리한 receipt_key가 다시 나타나면 경비 KB에 다시 저장하지 않는다.
- 중복으로 건너뛴 파일도 errors에 기록한다: `중복 영수증 receipt-cafe-01.png`

### 5. 경비 KB에 일괄 적재 — ingest_all() (src/app.py:91)

- `data/receipts/`의 영수증을 모두 처리한다.
- 각 영수증마다: 원문 추출 → 구조화 → 손상 건너뛰기 → 중복 건너뛰기 → 정상 레코드만 KB에 추가.
- 각 레코드에 원본 이미지의 확장자를 제외한 파일 식별자(`file`)를 저장한다.
- 완성된 레코드 목록을 `output/index.json`에 UTF-8(`ensure_ascii=False`)로 저장해 한글이 깨지지 않게 한다.

## 실행 결과 확인

```bash
python3 src/app.py
```

- 적재 리포트: loaded 3, skipped 2
  - errors: `읽기 실패 receipt-broken.png: 이미지 파일을 읽을 수 없습니다 (손상됨)`, `중복 영수증 receipt-cafe-01.png`
- `output/index.json`: 오로라카페 강남점(10,000원), 모범택시(18,700원), 오로라호텔 서울(187,000원) 3건

질의 4건 모두 정답 + `kb:` 출처 표기:

| 질문 | 답변 |
|---|---|
| 오로라카페 강남점에서 얼마를 사용했나요? | 10,000원 |
| 모범택시 이용 금액을 알려줘 | 18,700원 |
| 오로라호텔 서울의 경비 내역을 알려줘 | 객실료 150,000 + 조식 20,000 + 세금 17,000 = 187,000원 |
| 적재된 영수증은 모두 몇 건인가요? | 3건 |

## 적재 순서 특이점

파일명 정렬에서 `receipt-cafe-01-rescan.png`가 `receipt-cafe-01.png`보다 앞선다(`-` < `.`). 그 결과 재스캔본이 먼저 적재되고, 원본 파일명이 `중복 영수증 receipt-cafe-01.png`으로 errors에 기록된다 — 실습 지시 예시 출력과 일치하는 의도된 동작.

## LLM/VLM 연동 실전 기록

모델: openai/gpt-6-luna (mlapi.run, 2026-11-26)

- `temperature` 파라미터 미지원: `temperature: 0` → HTTP 400 "Only the default (1) value is supported". 페이로드에서 아예 빼야 한다.
- `max_tokens` 미지원 → `max_completion_tokens`를 사용해야 한다.
- reasoning_tokens를 소모하는 추론형 모델이라 완성 응답이 다소 지연된다.
- 400 진단 순서: `GET {BASE_URL}/models`로 모델명 확인 → 최소 텍스트 요청 → 페이로드에서 파라미터를 하나씩 제거하며 원인 특정.

자세한 연동 노하우는 [wiki/llm-integration.md](../wiki/llm-integration.md) 참고.

## 심화 활동 (기본 채점 제외)

- **저품질 영수증 처리**: `data/receipts/lowquality/`의 흐릿하거나 기울어진 영수증을 추가로 처리 — 현재는 스캔 대상에서 제외된 상태 (2026-11-26 결정).
- **품목 합계 검증**: 각 품목의 금액 합계와 영수증의 총액 일치 여부 확인.
- **경비 규정 검사**: 구조화된 영수증을 출장 규정과 비교해 한도 초과 경비 찾기.
- **영수증 검토 리포트**: 정상 적재, 중복, 손상, 합계 불일치 결과를 `output/`에 정리한 리포트.

## 배운 점

재사용 패턴과 교훈은 [wiki/Labs.md](../wiki/Labs.md) 실습 2 섹션으로 정리했다 — 전사·구조화 역할 분리, 내용 기반 중복 판정, 부분 실패 허용, 파일명 정렬 함정 등.
