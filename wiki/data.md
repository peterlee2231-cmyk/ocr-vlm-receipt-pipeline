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
