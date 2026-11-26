# -*- coding: utf-8 -*-
"""출장 경비 영수증 OCR/VLM 파이프라인.

학생 구현 함수
- extract_raw_text(): 영수증 이미지에서 원문 텍스트 추출
- extract_fields(): 원문을 구조화된 경비 레코드로 변환
- ingest_all(): 손상·중복 영수증을 제외하고 경비 KB에 일괄 적재

경비 분류와 KB 질의 기능은 완성본으로 제공됩니다.
"""
import json
import re
import time
from pathlib import Path

import llm

PROJECT_DIR = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = PROJECT_DIR / "data" / "receipts"
OUTPUT_DIR = PROJECT_DIR / "output"
INDEX_PATH = OUTPUT_DIR / "index.json"


_EXTRACT_INSTRUCTION = (
    "이미지는 출장 경비 영수증입니다. 영수증에 보이는 글자를 위에서 아래 순서로 읽어,"
    "이미지에 보이는 내용을 그대로 옮겨 적으세요.\n"
    "- 내용을 요약하거나 해석하지 않습니다.\n"
    "- 상호명, 날짜, 품목명, 금액을 빠뜨리지 않습니다.\n"
    "- 표 형태의 영수증도 각 행의 내용을 유지합니다.\n"
    "- 안내 문구나 주석 없이, 읽은 텍스트만 한 줄에 한 항목씩 출력합니다."
)


def extract_raw_text(image_path: str) -> str:
    """영수증 이미지 한 장의 원문 텍스트를 VLM으로 추출합니다."""
    raw = llm.extract_text(image_path, _EXTRACT_INSTRUCTION)
    return (raw or "").strip()


_CATEGORY_KEYWORDS = [("카페", "식비"), ("택시", "교통비"), ("호텔", "숙박비")]


def categorize(merchant: str) -> str:
    """상호명 키워드로 경비 항목을 분류합니다. (완성본)"""
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in merchant:
            return category
    return "기타"


def _parse_amount(text: str) -> int:
    """'4,500' 같은 금액 문자열에서 쉼표를 제거해 정수로 변환합니다."""
    return int(text.replace(",", ""))


def extract_fields(image_path: str) -> dict:
    """영수증 원문을 구조화된 경비 레코드로 변환합니다."""
    lines = [
        line.strip()
        for line in extract_raw_text(image_path).splitlines()
        if line.strip()
    ]
    if len(lines) < 3:
        raise ValueError(f"영수증 구조를 파악할 수 없습니다 (줄 수 부족): {Path(image_path).name}")

    merchant = lines[0]
    date = lines[1]

    items = []
    for line in lines[2:-1]:
        match = re.match(r"^(.+?)\s+([\d,]+)$", line)
        if not match:
            raise ValueError(f"품목 줄을 해석할 수 없습니다: {line!r}")
        items.append({"name": match.group(1), "amount": _parse_amount(match.group(2))})

    total_match = re.search(r"([\d,]+)", lines[-1])
    if not total_match:
        raise ValueError(f"합계 줄을 해석할 수 없습니다: {lines[-1]!r}")

    total = _parse_amount(total_match.group(1))
    return {
        "merchant": merchant,
        "date": date,
        "total": total,
        "category": categorize(merchant),
        "items": items,
        "receipt_key": f"{merchant}|{date}|{total}",
    }


def ingest_all() -> dict:
    """영수증을 일괄 처리하고 output/index.json에 저장합니다."""
    records: list[dict] = []
    errors: list[str] = []
    seen_keys: set[str] = set()

    for path in sorted(RECEIPTS_DIR.glob("*.png")):
        try:
            record = extract_fields(str(path))
        except Exception as exc:
            errors.append(f"읽기 실패 {path.name}: {exc}")
            continue

        if record["receipt_key"] in seen_keys:
            errors.append(f"중복 영수증 {path.name}")
            continue
        seen_keys.add(record["receipt_key"])

        record["file"] = path.stem
        records.append(record)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"loaded": len(records), "skipped": len(errors), "errors": errors}


# 경비 KB 질의 기능 (완성본)
_STATE = {"done": False, "report": None}


def _ensure_ingested() -> None:
    if _STATE["done"]:
        return
    try:
        _STATE["report"] = ingest_all()
    except Exception as exc:
        _STATE["report"] = {
            "loaded": 0,
            "skipped": 0,
            "errors": [f"적재 실패 {type(exc).__name__}: {exc}"],
        }
    _STATE["done"] = True


def _load_index() -> list:
    if not INDEX_PATH.exists():
        return []
    try:
        value = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def answer(question: str, mode=None) -> dict:
    """적재된 경비 KB를 바탕으로 질문에 답합니다. (완성본)"""
    started = time.perf_counter()
    _ensure_ingested()
    records = _load_index()
    text_question = question if isinstance(question, str) else ""

    matched = next(
        (
            record
            for record in records
            if isinstance(record, dict)
            and record.get("merchant")
            and record["merchant"] in text_question
        ),
        None,
    )

    if matched:
        context = json.dumps(matched, ensure_ascii=False)
        sources = [f"kb:{matched.get('file', 'unknown')}"]
    else:
        report = _STATE.get("report") or {}
        context = json.dumps(
            {
                "적재_건수": len(records),
                "건너뛴_건수": report.get("skipped", 0),
            },
            ensure_ascii=False,
        )
        sources = ["kb:index"]

    generated = llm.complete(text_question, context)
    return {
        "answer": generated if isinstance(generated, str) else "",
        "sources": sources,
        "metrics": {
            "latency_ms": (time.perf_counter() - started) * 1000,
            "cost": 0.0,
        },
    }


if __name__ == "__main__":
    report = ingest_all()
    print(json.dumps(report, ensure_ascii=False, indent=2))
