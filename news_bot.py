#!/usr/bin/env python3
# AI 뉴스 리포트 중계 봇 — 매일 정해진 시각에 Notion 통합 보고서 요약을 텔레그램 전송 (bot.py와 별도 상주 프로세스)
"""
뉴스봇 상주 프로세스(데몬).
  · 시계만 보는 단순 루프 — 텔레그램 getUpdates 를 절대 호출하지 않는다(409 방지).
  · daily_time 도달 시 run_report(): Notion 'AI NEWs' 페이지에서 오늘 자 통합 보고서를
    찾아 제목 + 핵심 요약 + 페이지 링크를 소유자에게 분할 전송.
  · 설정은 OUTPUT_DIR/news_settings.json, API 키는 OUTPUT_DIR/api_keys.json.
  · 외부 패키지 없이 표준 라이브러리만 사용.
"""
import os
import json
import time
import traceback
from datetime import datetime

import news_notion
from notify import notify_telegram, _load_telegram

# ── 경로 ──────────────────────────────────────────────────────
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
NEWS_SETTINGS_FILE = os.path.join(OUTPUT_DIR, "news_settings.json")
API_KEYS_FILE = os.path.join(OUTPUT_DIR, "api_keys.json")

DEFAULT_SETTINGS = {
    "daily_time": "10:00",
    "last_run_date": "",
}

DEFAULT_KEYS = {
    "notion": "",
}

# 'AI NEWs' 페이지 (직속 자식 탐색 — 실측 확인)
NOTION_PARENT_PAGE_ID = "396a0b7e561a80edbb31e60dcc86148a"

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _log(msg):
    print(f"[news] {msg}", flush=True)


# ── 설정 로드/저장 (직접 편집 파일이므로 값 검증 필수) ─────────────
def load_news_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    raw = {}
    corrected = False
    if os.path.exists(NEWS_SETTINGS_FILE):
        try:
            data = json.load(open(NEWS_SETTINGS_FILE, encoding="utf-8"))
            raw = {k: v for k, v in data.items() if k in DEFAULT_SETTINGS}
        except Exception as e:
            _log(f"news_settings.json 읽기 실패({e}) → 기본값 사용")
            corrected = True
    s.update(raw)

    # daily_time 검증 — HH:MM(제로패딩) 형식이 아니면 기본 10:00 으로 교정·저장.
    # strptime 만으로는 "8:00"(→08:00 해석)을 통과시켜 스케줄 비교(제로패딩 문자열)가
    # 어긋나므로, 파싱값을 다시 "%H:%M"으로 포맷해 원문과 완전 일치할 때만 유효로 본다.
    dt = str(s.get("daily_time", "")).strip()
    try:
        parsed = datetime.strptime(dt, "%H:%M")
        if parsed.strftime("%H:%M") != dt:
            raise ValueError("제로패딩 아님")
        s["daily_time"] = dt
    except (ValueError, TypeError):
        _log(f"daily_time 형식 오류(입력값: {s.get('daily_time')}) → 기본 10:00 사용")
        s["daily_time"] = "10:00"
        corrected = True

    # last_run_date 검증 — YYYY-MM-DD 아니면 "" (오늘 미실행으로 간주)
    lrd = str(s.get("last_run_date", "")).strip()
    if lrd:
        try:
            datetime.strptime(lrd, "%Y-%m-%d")
            s["last_run_date"] = lrd
        except (ValueError, TypeError):
            s["last_run_date"] = ""
            corrected = True
    else:
        s["last_run_date"] = ""

    # 파일이 없거나 교정이 있었으면 상태를 눈에 보이게 다시 저장
    if not os.path.exists(NEWS_SETTINGS_FILE) or corrected:
        save_news_settings(s)

    return s


def save_news_settings(s: dict) -> None:
    try:
        json.dump(s, open(NEWS_SETTINGS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"news_settings.json 저장 실패 — {e}")


def load_api_keys() -> dict:
    """OUTPUT_DIR/api_keys.json 로드. 없으면 빈 스키마로 자동 생성."""
    keys = dict(DEFAULT_KEYS)
    if os.path.exists(API_KEYS_FILE):
        try:
            data = json.load(open(API_KEYS_FILE, encoding="utf-8"))
            for k in DEFAULT_KEYS:
                v = data.get(k, "")
                keys[k] = str(v).strip() if v else ""
        except Exception as e:
            _log(f"api_keys.json 읽기 실패 — {e}")
    else:
        try:
            json.dump(DEFAULT_KEYS, open(API_KEYS_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            _log("api_keys.json 생성됨 — work 폴더에서 키를 채워 주세요")
        except Exception as e:
            _log(f"api_keys.json 생성 실패 — {e}")
    return keys


# ── 텔레그램 분할 전송 (03 §3.7) ──────────────────────────────
def send_long(text: str, chat_id: str) -> int:
    """4096자 제한 대응 분할 전송. 성공 조각 수 반환."""
    LIMIT = 3500

    def _split_long_line(line: str) -> list:
        """단일 줄이 LIMIT 초과 시 3500자 이내 마지막 공백에서 절단, 없으면 하드컷."""
        out = []
        while len(line) > LIMIT:
            window = line[:LIMIT]
            sp = window.rfind(" ")
            if sp > 0:
                out.append(line[:sp])
                line = line[sp + 1:]
            else:
                out.append(line[:LIMIT])
                line = line[LIMIT:]
        out.append(line)
        return out

    # 줄 단위 누적 — "버퍼 + 다음 줄"이 LIMIT 초과 시 버퍼 확정
    chunks = []
    buf = ""
    for line in text.split("\n"):
        # 단일 줄 자체가 LIMIT 초과면 먼저 잘게 나눔
        pieces = _split_long_line(line) if len(line) > LIMIT else [line]
        for i, piece in enumerate(pieces):
            candidate = piece if not buf else buf + "\n" + piece
            if len(candidate) > LIMIT and buf:
                chunks.append(buf)
                buf = piece
            else:
                buf = candidate
    if buf:
        chunks.append(buf)
    if not chunks:
        chunks = [""]

    total = len(chunks)
    sent = 0
    for i, chunk in enumerate(chunks, 1):
        body = f"[{i}/{total}]\n{chunk}" if total > 1 else chunk
        ok = notify_telegram(body, chat_id=chat_id)
        if ok:
            sent += 1
        else:
            _log(f"조각 {i}/{total} 전송 실패 — 나머지 계속 진행")
        if i < total:
            time.sleep(0.7)
    return sent


def _owner_chat_id() -> str:
    return _load_telegram().get("chat_id", "")


def _notify_failure(today: str, message: str):
    """실패 알림을 소유자에게 전송. 전송 자체가 실패하면 로그만 남긴다."""
    text = f"⚠️ AI 뉴스 리포트 실패 ({today})\n{message}"
    try:
        send_long(text, _owner_chat_id())
    except Exception as e:
        _log(f"실패 알림 전송 실패 — {e}")


# ── 실패 알림 문구 판별 (03 §3.2.4) ───────────────────────────
def _failure_hint(e: Exception) -> str:
    """예외를 상황별 실패 알림 문구로 변환. _get_json의 'HTTP {code} — …' 접두부로 판별."""
    msg = str(e)
    if msg.startswith("HTTP 401"):
        return ("Notion 인증 실패(401) — 토큰이 잘못됐거나 만료됐습니다. "
                "api_keys.json의 notion 키를 확인하세요.")
    if msg.startswith("HTTP 403"):
        return ("Notion 권한 부족(403) — 통합(integration)에 읽기 권한이 없습니다. "
                "Notion 통합 설정에서 콘텐츠 읽기 권한을 확인하세요.")
    if msg.startswith("HTTP 404"):
        return ("Notion 페이지 접근 불가(404) — 페이지가 없거나 통합(integration)에 "
                "공유되지 않았습니다. Notion에서 'AI NEWs' 페이지 → 연결(Connections)에 "
                "통합을 추가하세요.")
    if msg.startswith("HTTP 429"):
        return ("Notion 요청 제한(429) — 잠시 후 재시도해도 실패했습니다. "
                "내일 자동 재시도됩니다.")
    if msg.startswith("HTTP 5"):
        return ("Notion 서버 일시 장애 — 재시도해도 실패했습니다. "
                "내일 자동 재시도됩니다.")
    return f"내부 오류: {msg.splitlines()[0] if msg else type(e).__name__}"


# ── 파이프라인 본체 (Notion 통합 보고서 중계) ──────────────────
def run_report() -> None:
    now = datetime.now()                        # 컨테이너 TZ=Asia/Seoul
    today = now.strftime("%Y-%m-%d")
    today_disp = f"{today} ({_WEEKDAY_KR[now.weekday()]})"

    try:
        keys = load_api_keys()

        # 1) 토큰 없으면 외부 호출 전에 즉시 실패 알림
        if not keys.get("notion"):
            _notify_failure(today_disp,
                "Notion 토큰 없음 — work/api_keys.json에 notion 키를 입력하면 "
                "다음 날부터 동작합니다.")
            return

        # 2) 오늘 자 통합 보고서 child page 탐색 (중복 시 최신 편집본)
        found = news_notion.find_today_report(
            NOTION_PARENT_PAGE_ID, keys["notion"], f"통합 보고서_{today}")

        # 3) 없으면 ℹ️ 알림 1회 후 종료 (last_run_date는 main()이 기록 → 당일 재시도 없음, 사용자 승인)
        if not found:
            send_long(f"ℹ️ 오늘({today_disp}) 통합 보고서가 Notion에 아직 없습니다.\n"
                      "게시되면 내일 시각부터 자동 확인합니다.", _owner_chat_id())
            _log("오늘 리포트 없음 — 알림 후 종료")
            return

        page_id, title = found

        # 4) 리포트 페이지 블록 읽기 → 핵심 요약 추출
        blocks = news_notion.list_children(page_id, keys["notion"])
        summary = news_notion.extract_summary(blocks)   # 항상 비어있지 않은 문자열
        url = news_notion.page_url(page_id)

        # 5) 전송 — 제목 + 요약 + 링크 (전문 아님)
        msg = f"{title}\n\n{summary}\n\n📎 전문 보기(Notion)\n{url}"
        n = send_long(msg, _owner_chat_id())
        _log(f"리포트 중계 완료 — 조각 {n}개, 페이지 {page_id}")

    except Exception as e:
        # 어떤 예외에도 소유자에게 실패 알림 (기존 이중 방어 구조 유지)
        _log("run_report 내부 오류:\n" + traceback.format_exc())
        _notify_failure(today_disp, _failure_hint(e))


# ── 메인 루프 ────────────────────────────────────────────────
def main() -> None:
    try:
        keys = load_api_keys()
        s = load_news_settings()
        held = [name for name in DEFAULT_KEYS if keys.get(name)]
        _log(f"=== AI 뉴스봇 시작 === daily_time={s['daily_time']} 키보유: {', '.join(held) or '없음'}")
    except Exception:
        _log("시작 초기화 오류:\n" + traceback.format_exc())

    while True:
        try:
            s = load_news_settings()
            now = datetime.now()
            if now.strftime("%H:%M") >= s["daily_time"] and \
               s["last_run_date"] != now.strftime("%Y-%m-%d"):
                s["last_run_date"] = now.strftime("%Y-%m-%d")
                save_news_settings(s)   # 실행 '시작 직후' 기록 (03 §3.4 — 과금 반복 방지)
                run_report()
        except Exception:
            _log("메인 루프 오류:\n" + traceback.format_exc())
        time.sleep(20)


if __name__ == "__main__":
    main()
