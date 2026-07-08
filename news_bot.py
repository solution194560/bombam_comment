#!/usr/bin/env python3
# AI 뉴스 리포트 봇 — 매일 정해진 시각에 4개 LLM 조사→종합→텔레그램 전송 (bot.py와 별도 상주 프로세스)
"""
뉴스봇 상주 프로세스(데몬).
  · 시계만 보는 단순 루프 — 텔레그램 getUpdates 를 절대 호출하지 않는다(409 방지).
  · daily_time 도달 시 run_report(): 키 있는 제공자 병렬 조사 → Claude 종합 → 분할 전송.
  · 설정은 OUTPUT_DIR/news_settings.json, API 키는 OUTPUT_DIR/api_keys.json.
  · 외부 패키지 없이 표준 라이브러리만 사용.
"""
import os
import json
import time
import threading
import traceback
from datetime import datetime

import news_llm
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
    "xai": "",
    "openai": "",
    "zai": "",
    "anthropic": "",
}

# 제공자별 표시명·조사 함수·설정키 매핑
PROVIDERS = [
    ("xai", "Grok", "call_grok"),
    ("openai", "GPT", "call_openai"),
    ("zai", "GLM", "call_zai"),
    ("anthropic", "Claude", "call_claude_research"),
]

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


# ── 프롬프트 생성 (01 §3.5 / §3.6) ────────────────────────────
def build_research_prompt(today: str) -> str:
    return f"""오늘 날짜는 {today}입니다. 웹 검색을 사용해 아래 기준으로 뉴스를 조사·정리해 주세요.

[조사 범위]
AI, IT, 클라우드 인프라, 사이버보안/취약점/해킹 뉴스.

[기간 기준]
- 기준일은 오늘({today})입니다. 최근 24시간 뉴스를 우선하고, 부족하면 최근 3일까지
  확장하되 각 기사에 보도 날짜를 반드시 명기하세요.

[언어·출처]
- 최종 결과물은 한국어로 작성하세요 (외국어 기사는 번역·요약).
- 각 항목마다 원문 기사 링크가 반드시 있어야 합니다.

[정리 규칙]
- 같은 이슈를 다룬 기사는 하나로 묶고, 매체 간 관점 차이는 하위 항목으로 정리하세요.
- 카테고리는 4개입니다: ① AI ② IT ③ 클라우드 인프라 ④ 사이버보안·취약점·해킹.
  카테고리당 최대 10개 항목.
- 각 항목 형식: 제목 / 핵심 내용 / 왜 중요한가 / 관련 기업·기관 / 영향받는 분야 /
  출처(링크+보도날짜).
- 취약점 항목에는 가능하면 CVE 번호, 영향 제품/버전, 실제 악용 여부, 패치 유무를 포함하세요.

[마무리 — 전체 트렌드 요약]
- 오늘 가장 중요한 흐름 3가지
- 보안·AI·클라우드 실무자별 체크 포인트
- 향후 1~2주 추적할 이슈
- 과장 가능성이 있는 뉴스 vs 실제로 중요한 뉴스 구분

[주의]
- 확인되지 않은 내용은 "확인 필요"라고 명시하세요.
- 광고성 기사, 단순 주가 변동 기사는 제외하세요."""


def build_synthesis_prompt(today: str, results: dict, absent: dict) -> str:
    n = len(results)
    joined_names = ", ".join(results.keys())
    if absent:
        absent_desc = ", ".join(f"{name}({reason})" for name, reason in absent.items())
    else:
        absent_desc = "없음"

    # 종합 입력 절단 (03 §3.3) — [모델별 조사 결과] 앞부분
    body_map = {
        "Grok": "=== Grok(xAI) 조사 결과 ===",
        "GPT": "=== GPT(OpenAI) 조사 결과 ===",
        "GLM": "=== GLM-5.2(Z.AI) 조사 결과 ===",
        "Claude": "=== Claude(Anthropic) 조사 결과 ===",
    }
    sections = []
    for name, text in results.items():
        header = body_map.get(name, f"=== {name} 조사 결과 ===")
        sections.append(f"{header}\n{text}")
    results_block = "\n\n".join(sections)

    return f"""오늘 날짜는 {today}입니다. 아래에 서로 다른 AI 모델 {n}개({joined_names})가
같은 지시로 각자 웹 검색해 조사한 뉴스 리포트가 있습니다. 이를 교차검증해 하나의 최종
한국어 리포트로 종합해 주세요.
참고: {absent_desc}은(는) 이번 조사에 참여하지 못했습니다.

[병합 규칙]
1. 여러 모델이 공통으로 보도한 항목은 하나로 병합(중복 제거)하고, 세부 사실(날짜·수치·
   CVE 번호 등)이 일치하는지 교차검증하세요.
2. 모델 간 내용이 상충하면 어느 한쪽을 버리지 말고 "(상충) Grok: ○○ / GPT: ××" 형태로
   양쪽을 모두 표기하세요.
3. 한 모델만 보도한 항목은 항목 끝에 "(출처 모델: Grok)"처럼 어느 모델의 결과인지
   표기하고, 근거가 약해 보이면 "확인 필요"를 덧붙이세요.
4. 원문 기사 링크는 유지하되 같은 링크의 중복은 제거하세요. 링크가 전혀 없는 항목은
   "(링크 없음 — 확인 필요)"로 표기하세요.
5. 원 조사 지시의 구조를 그대로 유지하세요 — 카테고리 4개(AI / IT / 클라우드 인프라 /
   사이버보안·취약점·해킹), 카테고리당 최대 10개(중요도순으로 압축), 항목 형식
   (제목 / 핵심 내용 / 왜 중요한가 / 관련 기업·기관 / 영향받는 분야 / 출처(링크+보도날짜)),
   취약점 항목의 CVE·영향 버전·악용 여부·패치 유무.
6. 마지막의 전체 트렌드 요약(가장 중요한 흐름 3가지 / 보안·AI·클라우드 실무자별 포인트 /
   향후 1~2주 추적 이슈 / 과장 가능성 뉴스 vs 실제 중요 뉴스)도 모든 모델의 결과를
   종합해 새로 작성하세요.
7. 결과물은 텔레그램 일반 텍스트 메시지로 전송됩니다. 마크다운 문법(**, ##, 표, [텍스트](링크))
   을 쓰지 말고, 구분은 이모지·번호·줄바꿈만 사용하세요. 링크는 URL을 그대로 적으세요.
8. 광고성·단순 주가 기사는 제외하고, 확인되지 않은 내용은 "확인 필요"를 유지하세요.

[모델별 조사 결과]

{results_block}"""


# ── 종합 입력 절단 (03 §3.3) ──────────────────────────────────
def _truncate_result(text: str) -> str:
    """[검색 출처] URL 최대 30개 + 전체 12,000자 절단."""
    MAX_URLS = 30
    MAX_LEN = 12000

    # [검색 출처] 부록의 URL 을 최대 30개로 제한
    marker = "\n\n[검색 출처]\n"
    if marker in text:
        head, tail = text.split(marker, 1)
        lines = [ln for ln in tail.split("\n") if ln.strip()]
        # 중복 제거 후 최대 30개
        seen = []
        for ln in lines:
            if ln not in seen:
                seen.append(ln)
        seen = seen[:MAX_URLS]
        text = head + marker + "\n".join(seen)

    # 전체 12,000자 초과 시 마지막 줄바꿈에서 절단
    if len(text) > MAX_LEN:
        cut = text[:MAX_LEN]
        nl = cut.rfind("\n")
        if nl > 0:
            cut = cut[:nl]
        text = cut + "\n…(이하 원문 절단됨)"
    return text


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


# ── 파이프라인 본체 ──────────────────────────────────────────
def run_report() -> None:
    today_dt = datetime.now()
    today = f"{today_dt.strftime('%Y-%m-%d')} ({_WEEKDAY_KR[today_dt.weekday()]})"

    try:
        keys = load_api_keys()

        # Anthropic 키가 없으면 유료 조사 호출 전에 즉시 실패 알림 (03 §3.9)
        if not keys.get("anthropic"):
            _log("Anthropic 키 없음 — 종합 불가로 조사 호출 생략")
            _notify_failure(
                today,
                "Anthropic 키 없음 — 종합 단계 수행 불가.\n"
                "work/api_keys.json에 anthropic 키를 입력하면 다음 날부터 동작합니다.",
            )
            return

        prompt = build_research_prompt(today)

        results = {}
        absent = {}

        # 키 있는 제공자만 스레드 생성 (모듈 속성 경유 호출 — 몽키패치 가능)
        threads = []
        for key_name, disp, fn_name in PROVIDERS:
            if not keys.get(key_name):
                absent[disp] = "키 없음"
                continue
            t = threading.Thread(
                target=_run_provider,
                args=(fn_name, prompt, keys[key_name], disp, results, absent),
                daemon=True,
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()  # 무기한 대기 — 실제 상한은 urlopen(timeout=600) (03 §3.2)

        if not results:
            _log("참여 제공자 0개 — 실패 알림")
            _notify_failure(
                today,
                "모든 제공자 조사 실패(키 없음 또는 호출 실패).\n"
                + "\n".join(f"{name}: {reason}" for name, reason in absent.items())
                + "\n리포트를 만들 수 없었습니다. api_keys.json 확인 후 내일 자동 재시도됩니다.",
            )
            return

        # 종합 입력 절단 (03 §3.3)
        truncated = {name: _truncate_result(text) for name, text in results.items()}

        syn_prompt = build_synthesis_prompt(today, truncated, absent)

        # 종합 호출 (실패 시 10초 후 1회 재시도)
        report = None
        for attempt in range(2):
            try:
                report = news_llm.call_claude_synthesize(syn_prompt, keys["anthropic"])
                break
            except Exception as e:
                if attempt == 0:
                    _log(f"종합 호출 실패 — 10초 후 재시도 ({e})")
                    time.sleep(10)
                else:
                    _log(f"종합 호출 최종 실패 — {e}")

        if not report:
            _notify_failure(today, f"종합(Claude) 호출 실패.\n참여: {', '.join(results.keys())}")
            return

        # 헤더 부착 (01 §3.6) — 프로그램이 결정적으로 부착
        participated = ", ".join(results.keys())
        if absent:
            absent_line = ", ".join(f"{name}({reason})" for name, reason in absent.items())
        else:
            absent_line = "없음"
        header = (
            f"📰 AI·IT·보안 뉴스 리포트 — {today}\n"
            f"참여: {participated}\n"
            f"미참여: {absent_line}\n"
            "──────────────\n"
        )
        full = header + report

        n = send_long(full, _owner_chat_id())
        _log(f"리포트 전송 완료 — 참여 {len(results)}개, 조각 {n}개")

    except Exception as e:
        # 어떤 예외에도 소유자에게 실패 알림 (03 §3.4)
        _log("run_report 내부 오류:\n" + traceback.format_exc())
        _notify_failure(today, f"내부 오류: {str(e).splitlines()[0] if str(e) else type(e).__name__}")


def _run_provider(fn_name, prompt, api_key, disp, results, absent):
    """한 제공자 조사 호출. 실패 시 10초 후 1회 재시도, 그래도 실패면 미참여."""
    fn = getattr(news_llm, fn_name)
    for attempt in range(2):
        try:
            text = fn(prompt, api_key)
            if text and text.strip():
                results[disp] = text
                return
            raise RuntimeError("빈 응답")
        except Exception as e:
            reason = str(e).splitlines()[0] if str(e) else type(e).__name__
            if attempt == 0:
                _log(f"{disp} 조사 실패 — 10초 후 재시도 ({reason})")
                time.sleep(10)
            else:
                _log(f"{disp} 조사 최종 실패 — {reason}")
                if "빈 응답" in reason:
                    absent[disp] = "빈 응답"
                else:
                    absent[disp] = "호출 실패"


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
