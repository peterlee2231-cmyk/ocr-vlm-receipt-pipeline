# -*- coding: utf-8 -*-
"""LLM 호출 레이어 — VLM(이미지) 추출 + 텍스트 완성.

OpenAI 호환 API를 호출하여 결과를 반환합니다.
키가 없으면(API_KEY 미설정) 오프라인 mock 응답으로 동작합니다.
"""
import base64
import json
import os
import re
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """프로젝트 루트의 .env를 os.environ에 반영합니다(이미 설정된 값은 유지)."""
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env()

BASE_URL = os.environ.get(
    "BASE_URL",
    "https://mlapi.run/40cc17ae-a89b-4f12-a7d6-13293180fc87/v1",
)
MODEL = os.environ.get("MODEL", "openai/gpt-4o-mini")


def _api_key():
    key = os.environ.get("API_KEY", "").strip()
    return key if key.isascii() else ""


def _base_url():
    return BASE_URL.rstrip("/")


def _post(payload: dict) -> dict:
    request = urllib.request.Request(
        _base_url() + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


# ---------------------------------------------------------------- extract_text (vision)

RECEIPTS_DIR = PROJECT_DIR / "data" / "receipts"


PARTICLES = "은는이가을를의에서와과로도만"


_TRUTH = None


def _truth() -> dict:
    global _TRUTH
    if _TRUTH is None:
        _TRUTH = json.loads((RECEIPTS_DIR / "_truth.json").read_text(encoding="utf-8"))
    return _TRUTH


def _mock_extract_text(image_path: str) -> str:
    name = Path(image_path).stem
    entry = _truth().get(name)
    if entry is None:
        raise ValueError(f"등록되지 않은 이미지(mock 정답 없음): {name}")
    return entry["raw_text"]


def _tokens(text: str):
    toks = []
    for w in re.split(r"[^\w가-힣]+", text):
        if len(w) >= 2:
            toks.append(w)
            if w[-1] in PARTICLES and len(w) >= 3:
                toks.append(w[:-1])
    return toks


def _flatten(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _flatten(v, f"{prefix}{k} ")
    elif isinstance(obj, list):
        for v in obj:
            out += _flatten(v, prefix)
    else:
        out.append(f"{prefix.strip()} {obj}".strip())
    return out


def _mock_complete(question: str, context: str) -> str:
    """mock 답변 생성: context가 JSON이면 평문 문장으로 풀어 돌려준다."""
    try:
        data = json.loads(context)
        return "조회 결과: " + ", ".join(_flatten(data))
    except (ValueError, TypeError):
        return context


def _read_image_b64(image_path: str) -> str:
    """이미지 파일 → base64. PNG 매직바이트가 아니면 손상 파일로 간주해 예외를 던진다."""
    data = Path(image_path).read_bytes()
    if not data.startswith(b"\x89PNG"):
        raise ValueError(f"이미지 파일을 읽을 수 없습니다 (손상됨): {Path(image_path).name}")
    return base64.b64encode(data).decode()


def extract_text(image_path: str, instruction: str) -> str:
    """영수증 이미지 한 장을 VLM에 한 번 호출해 지시문(instruction)에 따라 텍스트를 추출한다.
    반환: VLM이 읽은 원문 텍스트(가공 전)."""
    b64 = _read_image_b64(image_path)  # 손상 파일이면 여기서 예외 발생 (호출자가 처리)
    if not _api_key():
        return _mock_extract_text(image_path)
    data = _post({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
    })
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- complete (text)

def complete(question: str, context: str) -> str:
    """경비 KB 조회 결과(context, JSON 문자열)를 근거로 질문에 대한 자연어 답변을 생성한다."""
    if not _api_key():
        return _mock_complete(question, context)
    data = _post({
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "다음 경비 KB 조회 결과(JSON)만 근거로 한국어 한 문장으로 간결히 답하라. "
                        "수치는 반올림하지 말고 그대로 인용하라. "
                        "JSON 형식(중괄호)을 그대로 출력하지 말 것.\n\n"
                        f"[조회 결과]\n{context}"},
            {"role": "user", "content": question},
        ],
    })
    return data["choices"][0]["message"]["content"]
