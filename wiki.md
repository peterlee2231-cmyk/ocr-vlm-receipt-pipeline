# 위키 번들 — 출장 경비 영수증 처리 파이프라인

wiki/ 폴더 전체를 한 파일로 모은 이식용 번들입니다. wiki/를 고치면 같은 커밋에서 이 번들도 재생성한다 (wiki/Home.md의 유지보수 규칙 참고).

---

## wiki/Home.md

# 지식 위키 — 출장 경비 영수증 처리 파이프라인

VLM으로 영수증 이미지의 원문을 추출하고, 경비 정보를 구조화해 손상·중복을 제외한 정상 영수증만 경비 KB(`output/index.json`)에 저장하는 파이프라인의 지식 문서입니다.

## 목차

| 페이지 | 내용 |
|---|---|
| [pipeline.md](pipeline.md) | 파이프라인 아키텍처 — 함수별 설계, 데이터 흐름, 실행·검증 결과 |
| [data.md](data.md) | 데이터 규격 — 영수증 이미지 구성, 경비 레코드 스키마, receipt_key 중복 판정 |
| [llm-integration.md](llm-integration.md) | LLM/VLM 연동 노하우 — 지시문 설계, mock 모드, API 제약 실전 기록, 오류 처리 |

## 유지보수 규칙

- 코드를 고친 커밋에서 위키의 라인 참조(`src/app.py:34` 형식)가 밀리지 않았는지 확인한다.
- `wiki/`의 페이지를 고치면 같은 커밋에서 루트의 `wiki.md`(단일 파일 번들)도 재생성해 둘을 동기화한다.
- git 없는 클라우드로 옮길 때는 `wiki.md` 번들 하나만 복사하면 위키 전체가 전달된다.
- `.env`(실제 API 키)는 위키·문서 어디에도 기록하지 않는다 — 값은 `.env`에만 존재한다.

---

## wiki/pipeline.md

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

---

## wiki/data.md

# 데이터 규격

## data/receipts 구성

| 파일 | 용도 |
|---|---|
| receipt-cafe-01.png | 정상 카페 영수증 (아메리카노 4,500 + 카페라떼 5,500 = 합계 10,000) |
| receipt-cafe-01-rescan.png | 동일 영수증의 재스캔 — receipt_key 중복 제외 대상 |
| receipt-taxi-01.png | 정상 택시 영수증 (이동요금 18,700) |
| receipt-hotel-01.png | 표형 호텔 청구서 (객실료 150,000 / 조식 20,000 / 세금 17,000 = 합계 187,000) |
| receipt-broken.png | PNG가 아닌 ASCII 텍스트 손상 파일 — 읽기 실패 대상 |
| lowquality/receipt-lowquality-01.png | 판독 불확실 영수증(`2026-06-1?`, `4,5OO`) — 스캔 대상에서 제외 |
| _truth.json | API_KEY가 없을 때 mock이 읽는 정답 raw_text (src/llm.py:79) |

- 스캔 대상은 최상위 `*.png`뿐이다. `lowquality/`는 파이프라인에 포함하지 않기로 결정했다(2026-11-26).

## 경비 레코드 스키마 (output/index.json 항목)

```json
{
    "merchant": "모범택시",
    "date": "2026-06-11",
    "total": 18700,
    "category": "교통비",
    "items": [
        {"name": "이동요금", "amount": 18700}
    ],
    "receipt_key": "모범택시|2026-06-11|18700",
    "file": "receipt-taxi-01"
}
```

- `extract_fields`(src/app.py:56)가 merchant~receipt_key까지 생성하고, `ingest_all`(src/app.py:91)이 `file`을 추가한다.
- `amount`/`total`은 쉼표를 제거한 정수다.
- `category` 분류 규칙: 상호명에 "카페"→식비, "택시"→교통비, "호텔"→숙박비, 그 외 "기타" (src/app.py:43).
- 표형 청구서(호텔)도 중간 줄이 하나의 품목이므로 같은 규격으로 items에 모두 저장된다.

## receipt_key 중복 판정

- 형식: `상호명|날짜|총액` (총액은 쉼표 없는 정수)
- 파일 이름이 달라도 key가 같으면 동일 영수증으로 판정한다.
- 먼저 처리한 key를 seen 집합에 보관하고, 같은 key가 다시 나오면 KB에 재저장하지 않고 errors에 `중복 영수증 {파일명}`을 기록한다 (src/app.py:91).
- 판정은 파일명이 아니라 내용 기반이므로 확장자·위치가 달라도 동일 내용이면 걸러진다.

## _truth.json

- 실제 VLM 호출(API_KEY 있음)에는 사용되지 않는다.
- mock 모드가 읽는 "가짜 외부 소스"로, 이미지 파일명(확장자 제외)을 키로 raw_text를 제공한다.
- 새 이미지를 추가해 mock으로 테스트하려면 이 파일에도 정답을 등록해야 한다.

---

## wiki/llm-integration.md

# LLM/VLM 연동 노하우

## 호출 레이어 (src/llm.py)

- `_post`(src/llm.py:48): OpenAI 호환 `/chat/completions`에 `urllib.request`로 POST한다. `BASE_URL`/`API_KEY`는 `_load_env`(src/llm.py:17)가 프로젝트 루트의 `.env`에서만 읽는다 — 코드에 키를 작성하지 않는다.
- `extract_text`(src/llm.py:127): 영수증 이미지 1장 → base64(`data:image/png`) → system에 전사 지시문, user에 image_url 건. 이미지당 VLM 호출 1회.
- `complete`(src/llm.py:148): KB 조회 결과(JSON)를 system에 넣고 질문을 user로 전달해 한국어 한 문장 답변을 생성한다.

## 전사 지시문 설계 (src/app.py:24)

- VLM에게 "해석"이 아니라 "전사"를 요구한다: 위→아래 순서 / 요약·해석 금지 / 상호명·날짜·품목·금액 누락 금지 / 보이는 내용 그대로 / 표는 행 단위 유지.
- 해석을 차단해야 줄 단위 파싱(`extract_fields`)이 예측 가능해진다 — 판독은 VLM, 구조화는 코드가 담당하는 역할 분리.
- 부가 설명·주석 출력 금지 조항을 넣어 응답이 순수 텍스트만 되도록 한다.

## 근거 기반 답변 프롬프트 (src/llm.py:156)

- "조회 결과(JSON)만 근거로" + "수치는 반올림 없이 그대로 인용" + "JSON 형식을 그대로 출력하지 말 것" — 환각 방지 3요소.

## mock 모드 (API_KEY 미설정 시)

- `_api_key`(src/llm.py:39)가 비어 있으면 실제 호출 대신 mock으로 동작한다.
- 원문 추출은 `_truth.json`의 raw_text를 반환하고(_mock_extract_text, src/llm.py:79), 답변 생성은 context JSON을 평문으로 풀어 반환한다(_mock_complete, src/llm.py:110).
- 오프라인 데모·회귀 테스트용이다. 새 이미지를 추가하면 mock 정답도 `_truth.json`에 등록해야 한다.

## API 제약 실전 기록 — openai/gpt-6-luna (mlapi.run, 2026-11-26)

- `temperature` 파라미터 미지원: `temperature: 0` → HTTP 400 "Only the default (1) value is supported". 페이로드에서 아예 빼야 한다(llm.py에서 제거함).
- `max_tokens` 미지원 → `max_completion_tokens`를 사용해야 한다.
- reasoning_tokens를 소모하는 추론형 모델이라 완성 응답이 다소 지연된다.
- 400 진단 순서: `GET {BASE_URL}/models`로 모델명 확인 → 최소 텍스트 요청 → 페이로드에서 파라미터를 하나씩 제거하며 원인 특정. 이 순서로 temperature가 원인임을 3번의 요청에 좁혔다.

## 오류 처리 원칙

- 손상 이미지는 `_read_image_b64`(src/llm.py:119)의 PNG 매직바이트(`\x89PNG`) 검사에서 즉시 ValueError — API 호출 전에 걸러진다.
- 한 파일의 예외가 전체 배치를 죽이지 않게 한다: `ingest_all`이 파일별 try/except로 흡수하고 errors에 파일명+사유를 기록한다.
- 판독 실패 내용을 임의로 채워 저장하지 않는다 — 모르면 건너뛴다.
