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
