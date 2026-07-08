# 4개 LLM(Grok/GPT/GLM/Claude) 뉴스 조사 API 호출 + Claude 종합 호출 — urllib만 사용
"""
4개 제공자 API 호출 모듈.
  · xAI Grok / OpenAI GPT / Z.AI GLM-5.2 / Anthropic Claude
  · 각 조사 함수는 (prompt, api_key) -> str 시그니처. 실패 시 예외를 던진다.
  · 종합 함수 call_claude_synthesize 도 (prompt, api_key) -> str.
  · 외부 패키지 없이 표준 라이브러리(urllib)만 사용.
"""
import json
import time
import urllib.request
import urllib.error


def _log(msg):
    print(f"[news] {msg}", flush=True)


def _post_json(url: str, headers: dict, body: dict, timeout: int = 600) -> dict:
    """JSON POST 1회 → JSON 응답 파싱. HTTP 오류 시 서버 응답 본문을 예외 메시지에 포함."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")
        except Exception:
            err_body = "(응답 본문 읽기 실패)"
        raise RuntimeError(f"HTTP {e.code} — {err_body[:500]}") from e


def _log_response_meta(provider: str, root: dict):
    """응답 루트 상위 키 목록 + stop_reason/finish_reason 을 로그로 남긴다(본문·키값 로그 금지)."""
    keys = list(root.keys()) if isinstance(root, dict) else []
    stop = root.get("stop_reason") if isinstance(root, dict) else None
    finish = None
    try:
        finish = root["choices"][0].get("finish_reason")
    except Exception:
        finish = None
    _log(f"{provider} 응답 상위키={keys} stop_reason={stop} finish_reason={finish}")


def _collect_sources(items) -> list:
    """인용 항목 리스트에서 URL 문자열만 뽑아 순서 유지·중복 제거."""
    urls = []
    if not items:
        return urls
    for it in items:
        url = None
        if isinstance(it, dict):
            url = it.get("url") or it.get("link")
        elif isinstance(it, str):
            url = it
        if url and url not in urls:
            urls.append(url)
    return urls


def _append_sources(text: str, urls: list) -> str:
    """본문 뒤에 [검색 출처] 부록을 붙인다."""
    if not urls:
        return text
    tail = "\n\n[검색 출처]\n" + "\n".join(urls)
    return text + tail


# ─────────────────────────────────────────────────────────────
# 1) xAI Grok — Responses API
# ─────────────────────────────────────────────────────────────
def call_grok(prompt: str, api_key: str) -> str:
    url = "https://api.x.ai/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "grok-4.3",
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search"}],
    }
    root = _post_json(url, headers, body)
    _log_response_meta("Grok", root)

    text = _extract_responses_text(root)

    # 인용: 루트 citations + output_text 블록의 annotations
    urls = _collect_sources(root.get("citations"))
    for item in root.get("output", []) or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for block in item.get("content", []) or []:
                if isinstance(block, dict):
                    for u in _collect_sources(block.get("annotations")):
                        if u not in urls:
                            urls.append(u)
    text = _append_sources(text, urls)

    if not text.strip():
        raise RuntimeError("빈 응답")
    return text


# ─────────────────────────────────────────────────────────────
# 2) OpenAI GPT — Responses API
# ─────────────────────────────────────────────────────────────
def call_openai(prompt: str, api_key: str) -> str:
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-5.5",
        "tools": [{"type": "web_search"}],
        "input": prompt,
    }
    root = _post_json(url, headers, body)
    _log_response_meta("GPT", root)

    text = _extract_responses_text(root)

    # 인용: message content 블록의 annotations
    urls = []
    for item in root.get("output", []) or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for block in item.get("content", []) or []:
                if isinstance(block, dict):
                    for u in _collect_sources(block.get("annotations")):
                        if u not in urls:
                            urls.append(u)
    text = _append_sources(text, urls)

    if not text.strip():
        raise RuntimeError("빈 응답")
    return text


def _extract_responses_text(root: dict) -> str:
    """xAI·OpenAI Responses API 공통 파싱.
       output_text 가 있으면 우선, 없으면 output[]의 message content 블록의 .text 전부 이어붙임."""
    ot = root.get("output_text")
    if isinstance(ot, str) and ot.strip():
        return ot
    parts = []
    for item in root.get("output", []) or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for block in item.get("content", []) or []:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
    return "".join(parts)


# ─────────────────────────────────────────────────────────────
# 3) Z.AI GLM-5.2 — OpenAI 호환 chat/completions
# ─────────────────────────────────────────────────────────────
def call_zai(prompt: str, api_key: str) -> str:
    url = "https://api.z.ai/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_result": True,
                "search_recency_filter": "oneWeek",
            },
        }],
    }
    root = _post_json(url, headers, body)
    _log_response_meta("GLM", root)

    text = ""
    try:
        text = root["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"응답 구조 이상 — {e}")

    # 루트 web_search[] (title/link/publish_date) 를 [검색 출처] 부록으로
    urls = _collect_sources(root.get("web_search"))
    text = _append_sources(text, urls)

    if not text.strip():
        raise RuntimeError("빈 응답")
    return text


# ─────────────────────────────────────────────────────────────
# 4) Anthropic Claude — 조사 호출 (web_search 도구 + pause_turn 재개 루프)
# ─────────────────────────────────────────────────────────────
def call_claude_research(prompt: str, api_key: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 15}]

    collected = []
    start = time.time()
    MAX_PAUSE = 5          # pause_turn 최대 재개 횟수 (01 §3.4)
    WALL_LIMIT = 1800      # 벽시계 상한 30분 (03 §3.2)
    pause_count = 0

    while True:
        body = {
            "model": "claude-opus-4-8",
            "max_tokens": 16000,
            "tools": tools,
            "messages": messages,
        }
        root = _post_json(url, headers, body)
        _log_response_meta("Claude(조사)", root)

        content = root.get("content", []) or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                collected.append(block["text"])

        stop = root.get("stop_reason")

        if stop == "pause_turn":
            pause_count += 1
            elapsed = time.time() - start
            if pause_count > MAX_PAUSE or elapsed > WALL_LIMIT:
                _log(f"Claude(조사) pause 중단 — pause={pause_count}회 경과={int(elapsed)}초")
                break
            # 이번 응답의 assistant content 전체를 붙여 재요청
            messages.append({"role": "assistant", "content": content})
            continue

        if stop == "refusal":
            raise RuntimeError("stop_reason=refusal")

        if stop == "max_tokens":
            _log("Claude(조사) max_tokens 도달 — 잘린 텍스트 반환")

        break

    text = "".join(collected)
    if not text.strip():
        raise RuntimeError("빈 응답")
    return text


# ─────────────────────────────────────────────────────────────
# 5) Anthropic Claude — 종합 호출 (도구 없음, 1회)
# ─────────────────────────────────────────────────────────────
def call_claude_synthesize(prompt: str, api_key: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    messages = [{"role": "user", "content": prompt}]

    collected = []
    start = time.time()
    MAX_PAUSE = 5
    WALL_LIMIT = 1800
    pause_count = 0

    while True:
        body = {
            "model": "claude-opus-4-8",
            "max_tokens": 16000,
            "messages": messages,
        }
        root = _post_json(url, headers, body)
        _log_response_meta("Claude(종합)", root)

        content = root.get("content", []) or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                collected.append(block["text"])

        stop = root.get("stop_reason")

        if stop == "pause_turn":
            pause_count += 1
            elapsed = time.time() - start
            if pause_count > MAX_PAUSE or elapsed > WALL_LIMIT:
                _log(f"Claude(종합) pause 중단 — pause={pause_count}회 경과={int(elapsed)}초")
                break
            messages.append({"role": "assistant", "content": content})
            continue

        if stop == "refusal":
            raise RuntimeError("stop_reason=refusal")

        if stop == "max_tokens":
            _log("Claude(종합) max_tokens 도달 — 잘린 리포트 그대로 전송")

        break

    text = "".join(collected)
    if not text.strip():
        raise RuntimeError("빈 응답")
    return text
