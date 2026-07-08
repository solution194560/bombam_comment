# Notion API 호출 모듈 — 부모 페이지의 child page 탐색·블록 읽기·핵심 요약 추출 (urllib만 사용)
import json
import time
import urllib.error
import urllib.parse
import urllib.request

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"   # 안정 버전 확정 — 시나리오 6에서 실호출로 응답 형태 검증
TIMEOUT = 30                     # urlopen 타임아웃(초)

# 일시 장애로 보고 1회 재시도할 상태코드
_RETRY_CODES = {429, 500, 502, 503, 504, 529}


def _get_json(url: str, token: str) -> dict:
    """GET 요청 후 JSON dict 반환. 429·5xx·529는 Retry-After 기반 1회 재시도, 그 외는 즉시 예외."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    for attempt in range(2):   # 최초 + 재시도 1회
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            # 일시 장애면 딱 1회만 재시도
            if e.code in _RETRY_CODES and attempt == 0:
                delay = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = min(float(delay), 30)
                except (TypeError, ValueError):
                    wait = 2
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code} — {body[:500]}")


def list_children(block_id: str, token: str) -> list:
    """block_id의 자식 블록 전체를 페이지네이션(100개씩) 감춰서 반환. 중첩 재귀는 안 한다."""
    base = f"{NOTION_API}/blocks/{block_id}/children"
    results = []
    cursor = None
    for _ in range(10):                      # 안전 상한 10페이지(블록 1,000개)
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        root = _get_json(base + "?" + urllib.parse.urlencode(params), token)
        results += root.get("results", [])
        if not root.get("has_more"):
            return results
        cursor = root.get("next_cursor")
        if not cursor:
            return results
    raise RuntimeError("Notion pagination limit exceeded")   # 10페이지 초과 — 조용한 반환 금지


def find_today_report(parent_id: str, token: str, needle: str):
    """parent_id 직속 child_page 중 제목에 needle이 포함된 것을 찾아 (id, title) 반환. 없으면 None."""
    matches = []
    for block in list_children(parent_id, token):
        if block.get("type") != "child_page":
            continue
        title = block.get("child_page", {}).get("title", "")
        if needle in title:
            matches.append(block)

    if not matches:
        return None

    if len(matches) > 1:
        # last_edited_time(ISO 8601 UTC)은 사전순=시간순이라 파싱 없이 문자열 max 로 최신본 선택
        print(f"[notion] 동일 제목 {len(matches)}개 중복 — 최신 편집본 선택", flush=True)
        best = max(matches, key=lambda b: b.get("last_edited_time", ""))
    else:
        best = matches[0]

    return best["id"], best.get("child_page", {}).get("title", "")


def rich_text_to_plain(rich_text: list) -> str:
    """rich_text 배열의 plain_text 를 이어붙여 반환(서식은 무시)."""
    return "".join(rt.get("plain_text", "") for rt in rich_text)


def _block_line(block: dict):
    """모을 대상 블록이면 한 줄 텍스트를 반환, 아니면 None."""
    btype = block.get("type")
    if btype == "paragraph":
        return rich_text_to_plain(block.get("paragraph", {}).get("rich_text", []))
    if btype == "bulleted_list_item":
        return "• " + rich_text_to_plain(block.get("bulleted_list_item", {}).get("rich_text", []))
    if btype == "numbered_list_item":
        return "• " + rich_text_to_plain(block.get("numbered_list_item", {}).get("rich_text", []))
    if btype == "quote":
        return rich_text_to_plain(block.get("quote", {}).get("rich_text", []))
    return None


_HEADING_LEVEL = {"heading_1": 1, "heading_2": 2, "heading_3": 3}


def extract_summary(blocks: list) -> str:
    """최상위 블록에서 '핵심 요약(Executive Summary)' 섹션을 추출. 빈 문자열은 절대 반환하지 않는다."""
    # 1차 규칙 — 핵심 요약 heading 찾기
    start = None
    start_level = None
    for i, block in enumerate(blocks):
        btype = block.get("type")
        level = _HEADING_LEVEL.get(btype)
        if level is None:
            continue
        htext = rich_text_to_plain(block.get(btype, {}).get("rich_text", []))
        if "핵심 요약" in htext or "executive summary" in htext.lower():
            start = i
            start_level = level
            break

    if start is not None:
        lines = []
        for block in blocks[start + 1:]:
            btype = block.get("type")
            level = _HEADING_LEVEL.get(btype)
            # 시작 heading과 같거나 상위(숫자 같거나 작음) heading 을 만나면 종료
            if level is not None and level <= start_level:
                break
            line = _block_line(block)
            if line and line.strip():
                lines.append(line)
        body = "\n".join(lines)
        if body.strip():
            return body

    # 폴백 1 — 본문 앞부분 최대 1,000자
    lines = []
    for block in blocks:
        line = _block_line(block)
        if line and line.strip():
            lines.append(line)
    head = "\n".join(lines)
    if head.strip():
        if len(head) > 1000:
            cut = head[:1000]
            nl = cut.rfind("\n")
            if nl > 0:
                cut = cut[:nl]
            head = cut + "…(이하 생략 — 전문은 링크 참고)"
        return "(핵심 요약 섹션을 찾지 못해 본문 앞부분을 표시합니다)\n" + head

    # 폴백 2 — 링크 안내 문구
    return "(요약을 추출하지 못했습니다 — 전문은 아래 링크에서 확인하세요)"


def page_url(block_id: str) -> str:
    """child_page 블록 id(UUID)에서 대시를 제거한 32자 hex가 곧 Notion 페이지 주소."""
    return "https://www.notion.so/" + block_id.replace("-", "")
