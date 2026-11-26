# OCR/VLM 기반 출장 경비 영수증 처리 파이프라인

VLM으로 카페·택시·호텔 영수증 이미지의 원문을 추출하고, 경비 정보를 구조화한 뒤 손상·중복 영수증을 제외해 정상 영수증만 경비 KB에 저장합니다. 저장된 KB는 자연어 질의에 답하는 데 사용됩니다.

## 동작 개요

```
data/receipts/*.png (파일명 순)
  → extract_raw_text()  VLM 원문 전사 (해석 없이 그대로)
  → extract_fields()    줄 단위 구조화 — 상호명·날짜·품목·총액·분류·receipt_key
  → 손상 파일 건너뛰기 / receipt_key 중복 제외
  → output/index.json   경비 KB 저장 + 리포트 {loaded, skipped, errors}
  → answer()            KB 조회 결과를 근거로 자연어 답변 생성
```

- 하나의 이미지에서 오류가 발생해도 전체 적재는 중단되지 않습니다 — 건너뛴 파일과 오류 내용은 리포트의 errors에 기록됩니다.
- 판독에 실패한 내용을 임의로 만들어 저장하지 않습니다.

## 프로젝트 구조

```
├── src/
│   ├── app.py          # 파이프라인 본체 — 원문 추출·구조화·적재·KB 질의
│   └── llm.py          # LLM API 연동 — VLM 원문 추출 + 텍스트 완성 (mock 폴백 포함)
├── data/receipts/      # 영수증 이미지 + lowquality/ + mock 정답(_truth.json)
├── output/             # index.json — 경비 KB (적재 결과)
├── wiki/               # LLM 활용 지식 위키 — Home.md가 인덱스
├── wiki.md             # 위키 단일 파일 번들 — 다른 클라우드 이식용
└── read.md             # 이 문서
```

## 실행 방법

```bash
# 1) 환경변수 설정 — 프로젝트 루트의 .env에 API_KEY, BASE_URL, MODEL 작성
#    (실제 키는 .env에만 두고 코드에 작성하지 않습니다. .env는 커밋 대상이 아닙니다.)

# 2) 영수증 일괄 적재 — 리포트 출력 + output/index.json 생성
python3 src/app.py

# 3) 적재된 경비 KB 질의 (예시)
python3 -c "import sys; sys.path.insert(0,'src'); import app; print(app.answer('오로라카페 강남점에서 얼마를 사용했나요?')['answer'])"
```

Python 표준 라이브러리만 사용하며 외부 패키지 설치가 필요 없습니다.

## 경비 레코드 규격 (output/index.json 항목)

```json
{
    "merchant": "모범택시",
    "date": "2026-06-11",
    "total": 18700,
    "category": "교통비",
    "items": [{"name": "이동요금", "amount": 18700}],
    "receipt_key": "모범택시|2026-06-11|18700",
    "file": "receipt-taxi-01"
}
```

- category: 상호명 키워드 분류 (카페→식비, 택시→교통비, 호텔→숙박비, 그 외 기타)
- receipt_key: `상호명|날짜|총액` — 파일명이 달라도 동일 영수증으로 판정하는 기준

## 적재 규칙

| 상황 | 처리 |
|---|---|
| 정상 영수증 | 구조화해 KB에 저장 |
| 손상 이미지 (PNG 형식 아님) | 건너뛰고 errors에 `읽기 실패 {파일}: {사유}` 기록 |
| receipt_key 중복 | 뒤에 온 파일 건너뛰고 errors에 `중복 영수증 {파일}` 기록 |
| lowquality/ 하위 폴더 | 스캔 대상에서 제외 |

## 참고

- LLM/VLM 통합 노하우(아키텍처·데이터 규격·프롬프트·API 제약)는 [wiki/Home.md](wiki/Home.md)에서 정리합니다.
- `.env`(실제 API 키)는 커밋에서 제외됩니다 (.gitignore 등록).
