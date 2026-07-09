# Grok 웹 자동화 봇 — 매일 아침 grok.com에서 뉴스 보고서를 생성시켜 Notion에 업로드 (별도 상주 프로세스)
"""
Grok 뉴스 보고서 상주 프로세스(데몬).
  · 시계만 보는 단순 루프 — 텔레그램 getUpdates 를 절대 호출하지 않는다(409 무관).
  · daily_time 도달 시 grok.com 에 저장 프로필로 접속해 프롬프트를 전송, 응답을 수집해
    Notion 'AI NEWs' 하위에 "Grok news_{YYYY-MM-DD}" 페이지로 업로드한다.
  · 실패 시 소유자에게 실패 알림 1건 + retry_at(30분 뒤) 1회 자동 재시도(하루 최대 2회 시도).
  · 설정은 OUTPUT_DIR/grok_settings.json, Notion 토큰은 OUTPUT_DIR/api_keys.json 의 notion 키.
  · 리디 수집과 브라우저 동시 구동을 browser_lock 으로 막는다(2GB RAM OOM 방지).
"""
import os
import sys
import json
import time
import hashlib
import traceback
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

import news_notion
import browser_lock
from notify import notify_telegram, _load_telegram

# ── 경로·상수 ────────────────────────────────────────────────
GROK_URL = "https://grok.com"
GROK_PROFILE = os.environ.get("GROK_PROFILE", "/app/.grok_profile")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
GROK_SETTINGS_FILE = os.path.join(OUTPUT_DIR, "grok_settings.json")
API_KEYS_FILE = os.path.join(OUTPUT_DIR, "api_keys.json")
PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grok_prompt.txt")
NOTION_PARENT_PAGE_ID = "396a0b7e561a80edbb31e60dcc86148a"
HEADLESS = os.environ.get("HEADLESS", "1") != "0"   # 리디와 동일 규칙(0=실제 창)

DEFAULT_GROK_SETTINGS = {
    "daily_time": "07:00",
    "last_run_date": "",
    "retry_at": "",
}

# 완료 감지 파라미터 (§3.3 — probe 실측으로 조정 가능)
# TODO(probe): 실제 완주 로그(총 소요·중간 정지 길이)로 아래 값 재조정
_MIN_ELAPSED = 90     # 전송 후 최소 경과(초) — 검색 준비 단계의 짧은 정지를 완료로 오판 방지
_STABLE_SEC = 60      # 연속 무변화(안정화 창, 초)
_HARD_TIMEOUT = 1200  # 하드 타임아웃(초) = 20분

# 보조 신호 B(생성 중 정지 버튼 소실) — probe 로 동작 확인 전엔 끈다(오판 방지)
# TODO(probe): 정지 버튼 셀렉터·동작 확인 후 True 로 켜기
_STOP_SIGNAL_ENABLED = False

# grok.com 셀렉터 후보 — CSS-in-JS 해시 클래스명 금지(함정 10). 태그·aria-label·placeholder만.
# TODO(probe): 아래 후보를 실제 grok.com DOM 으로 확인해 확정
_PROMPT_SELECTORS = [
    "textarea",
    'div[contenteditable="true"]',
    '[aria-label*="Ask" i]',
    '[placeholder*="Ask" i]',
    '[aria-label*="Grok" i]',
    '[placeholder*="Grok" i]',
]
# TODO(probe): 응답(마지막 대화 블록) 실제 셀렉터 확인 후 확정
_RESPONSE_SELECTORS = [
    "[data-testid*='message' i]",
    "[data-message-author-role]",
    "article",
]

_LAST_PROMPT = ""   # 폴백 추출 시 프롬프트 원문 접두부 제거용


def _log(msg):
    print(f"[grok] {msg}", flush=True)


# ── 설정 로드/저장 (직접 편집 파일이므로 값 검증 필수 — news_bot 패턴) ──
def load_grok_settings() -> dict:
    s = dict(DEFAULT_GROK_SETTINGS)
    raw = {}
    corrected = False
    if os.path.exists(GROK_SETTINGS_FILE):
        try:
            data = json.load(open(GROK_SETTINGS_FILE, encoding="utf-8"))
            raw = {k: v for k, v in data.items() if k in DEFAULT_GROK_SETTINGS}
        except Exception as e:
            _log(f"grok_settings.json 읽기 실패({e}) → 기본값 사용")
            corrected = True
    s.update(raw)

    # daily_time — HH:MM(제로패딩) 아니면 07:00 교정(제로패딩 문자열 비교가 어긋나지 않게)
    dt = str(s.get("daily_time", "")).strip()
    try:
        parsed = datetime.strptime(dt, "%H:%M")
        if parsed.strftime("%H:%M") != dt:
            raise ValueError("제로패딩 아님")
        s["daily_time"] = dt
    except (ValueError, TypeError):
        _log(f"daily_time 형식 오류(입력값: {s.get('daily_time')}) → 기본 07:00 사용")
        s["daily_time"] = "07:00"
        corrected = True

    # last_run_date — YYYY-MM-DD 아니면 "" (오늘 미실행으로 간주)
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

    # retry_at — "YYYY-MM-DD HH:MM:SS"(bot.py 포맷) 아니면 ""
    rat = str(s.get("retry_at", "")).strip()
    if rat:
        try:
            datetime.strptime(rat, "%Y-%m-%d %H:%M:%S")
            s["retry_at"] = rat
        except (ValueError, TypeError):
            s["retry_at"] = ""
            corrected = True
    else:
        s["retry_at"] = ""

    if not os.path.exists(GROK_SETTINGS_FILE) or corrected:
        save_grok_settings(s)

    return s


def save_grok_settings(s: dict) -> None:
    try:
        json.dump(s, open(GROK_SETTINGS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"grok_settings.json 저장 실패 — {e}")


def _load_notion_token() -> str:
    """OUTPUT_DIR/api_keys.json 의 notion 토큰을 반환. 없으면 빈 문자열."""
    try:
        data = json.load(open(API_KEYS_FILE, encoding="utf-8"))
        v = data.get("notion", "")
        return str(v).strip() if v else ""
    except Exception as e:
        _log(f"api_keys.json 읽기 실패 — {e}")
        return ""


# ── 텔레그램 실패 알림 (소유자 1건) ───────────────────────────
def _owner_chat_id() -> str:
    return _load_telegram().get("chat_id", "")


def _notify_failure(today: str, message: str) -> None:
    """실패 알림을 소유자에게 전송. 전송 자체가 실패하면 로그만 남긴다(news_bot 패턴)."""
    text = f"⚠️ Grok 뉴스 보고서 실패 ({today})\n{message}"
    try:
        notify_telegram(text, chat_id=_owner_chat_id())
    except Exception as e:
        _log(f"실패 알림 전송 실패 — {e}")


def _schedule_retry(today: str) -> None:
    """정기 실행 실패 시 30분 뒤 1회 재시도를 예약(retry_at 기록)."""
    s = load_grok_settings()
    s["retry_at"] = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    save_grok_settings(s)
    _log("30분 뒤 1회 재시도 예약(retry_at 기록)")


# ── 브라우저 헬퍼 (리디 패턴 자체 구현 — ridi_collector import 안 함) ──
def _clear_singleton_locks() -> None:
    """GROK_PROFILE 안 SingletonLock/Cookie/Socket 잔여 락 삭제(함정 4)."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        p = os.path.join(GROK_PROFILE, name)
        try:
            if os.path.islink(p) or os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _new_grok_browser(p):
    mode = "headless(창 없음)" if HEADLESS else "실제 창"
    _log(f"브라우저 {mode} 모드로 실행 (프로필={GROK_PROFILE})")
    return p.chromium.launch_persistent_context(
        user_data_dir=GROK_PROFILE, headless=HEADLESS,
        viewport={"width": 1280, "height": 900},
        # 저사양/컨테이너 안정화 플래그 (--disable-dev-shm-usage: /dev/shm 작은 환경 필수)
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
              '--disable-gpu', '--start-maximized'],
        permissions=["clipboard-read"])   # 복사 버튼 → 클립보드 best-effort 경로용


def _wait_cloudflare(page, limit=90) -> bool:
    """Cloudflare 'Just a moment' 화면이 사라질 때까지 대기(진행 표시)."""
    for i in range(limit):
        if "Just a moment" not in (page.title() or ""):
            return True
        if i == 0:
            print("  [대기] Cloudflare 통과 대기 중...", end="", flush=True)
        else:
            print(".", end="", flush=True)
        time.sleep(1)
    print()
    return False


def _find_prompt_input(page):
    """프롬프트 입력창 locator 를 후보 순서대로 탐색해 첫 가시 요소 반환. 없으면 None."""
    for sel in _PROMPT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _is_logged_in(page) -> bool:
    """프롬프트 입력창 존재 여부로 로그인 상태 판단(입력창 없으면 미로그인)."""
    return _find_prompt_input(page) is not None


def _submit_prompt(page, text) -> None:
    """입력창에 프롬프트를 넣고 전송. 입력창을 못 찾으면 명확히 예외(조용한 오작동 금지)."""
    global _LAST_PROMPT
    _LAST_PROMPT = text
    inp = _find_prompt_input(page)
    if inp is None:
        raise RuntimeError("grok.com 프롬프트 입력창을 찾지 못함 — 화면 구조 변경 의심")
    inp.click()
    try:
        inp.fill(text)               # textarea·contenteditable 모두 지원
    except Exception:
        page.keyboard.type(text)     # 폴백 — 직접 타이핑
    # 전송 — Enter 우선(§3.3). Enter 가 안 먹는 UI 대비 전송 버튼 폴백.
    # TODO(probe): Enter 전송 여부 확인. 줄바꿈만 되면 아래 버튼 셀렉터로 확정
    try:
        inp.press("Enter")
    except Exception:
        for sel in ('button[type="submit"]',
                    'button[aria-label*="Send" i]',
                    'button[aria-label*="Submit" i]'):
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=3000)
                    return
            except Exception:
                continue
        raise RuntimeError("grok.com 전송 수단을 찾지 못함 — 화면 구조 변경 의심")


def _stop_button_gone(page) -> bool:
    """보조 신호 B — 생성 중 정지 버튼이 사라졌는지. 사용 가능 확인 전엔 항상 False."""
    if not _STOP_SIGNAL_ENABLED:
        return False
    try:
        return page.locator('button[aria-label*="Stop" i]').count() == 0
    except Exception:
        return False


def _response_text(page) -> str:
    """응답 영역 텍스트를 best-effort 로 반환(폴링·품질검사 겸용, innerText 기반)."""
    for sel in _RESPONSE_SELECTORS:
        try:
            loc = page.locator(sel).last
            if loc.count() > 0:
                t = loc.inner_text()
                if t and t.strip():
                    return t
        except Exception:
            continue
    # 폴백 — main 본문 innerText 에서 프롬프트 원문 이후 부분
    body = ""
    try:
        body = page.locator("main").last.inner_text()
    except Exception:
        try:
            body = page.evaluate("() => document.body.innerText") or ""
        except Exception:
            body = ""
    if _LAST_PROMPT:
        marker = _LAST_PROMPT[:80]
        idx = body.rfind(marker)
        if idx >= 0:
            body = body[idx + len(marker):]
    return body


def _wait_response_done(page, hard_timeout=_HARD_TIMEOUT, require_last_section=True) -> bool:
    """완료 감지 — 최소 경과 + 연속 무변화 + (마지막 섹션 존재 또는 보조 신호). 초과 시 False."""
    start = time.time()
    last_sig = None
    last_change = start
    last_log = 0.0
    while True:
        now = time.time()
        elapsed = now - start
        if elapsed > hard_timeout:
            _log(f"응답 대기 하드 타임아웃({hard_timeout // 60}분) 초과 — 실패 처리")
            return False
        text = _response_text(page)
        sig = f"{len(text)}:{hashlib.md5(text.encode('utf-8', 'replace')).hexdigest()}"
        if sig != last_sig:
            last_sig = sig
            last_change = now
        stable_for = now - last_change
        # 60초에 1번꼴로만 진행 로그(§6.6 — 20분 대기 로그 도배 방지)
        if now - last_log >= 60:
            _log(f"응답 생성 대기 중 — 경과 {elapsed:.0f}s, 무변화 {stable_for:.0f}s, 길이 {len(text)}")
            last_log = now
        cond3 = (not require_last_section) or _has_last_section(text) or _stop_button_gone(page)
        if elapsed >= _MIN_ELAPSED and stable_for >= _STABLE_SEC and cond3:
            _log(f"응답 완료 감지 — 경과 {elapsed:.0f}s, 길이 {len(text)}")
            return True
        time.sleep(5)


def _try_clipboard(page):
    """복사 버튼 → navigator.clipboard.readText() best-effort. 어느 단계든 실패하면 None."""
    # TODO(probe): 복사 버튼 셀렉터·클립보드 권한 동작 확인
    try:
        btn = page.locator('button[aria-label*="Copy" i]').last
        if btn.count() == 0:
            return None
        btn.click(timeout=3000)
        page.wait_for_timeout(500)
        return page.evaluate("() => navigator.clipboard.readText()")
    except Exception:
        return None


def _extract_report(page) -> str:
    """응답 텍스트 수집 — 복사버튼→클립보드 best-effort 우선, 실패 시 innerText 정상 경로."""
    txt = _try_clipboard(page)
    if txt and txt.strip():
        return txt.strip()
    return _response_text(page).strip()


def _has_last_section(text: str) -> bool:
    return ("종합 트렌드" in text) or ("권고" in text)


def _quality_gate(text: str):
    """통과면 None, 미달이면 사유 문자열 반환(불량 보고서 업로드 차단 — 함정 6 취지)."""
    if len(text) < 1500:
        return "응답이 너무 짧음(1,500자 미만) — 오류/거절 응답 의심"
    low = text.lower()
    if "개요" not in text and "executive summary" not in low:
        return "필수 섹션(개요/Executive Summary) 누락"
    if not _has_last_section(text):
        return "마지막 섹션(종합 트렌드/권고) 누락 — 중간 절단 의심"
    return None


def _load_prompt(today: str) -> str:
    with open(PROMPT_FILE, encoding="utf-8") as f:
        return f.read().replace("{현재 날짜}", today)


# ── 1회 실행 본체 (§3.1의 1~15) ───────────────────────────────
def run_grok_report(record_retry: bool = True) -> None:
    today = datetime.now().strftime("%Y-%m-%d")

    def fail(msg, schedule=True):
        _log(f"실패 — {msg}")
        _notify_failure(today, msg)
        if record_retry and schedule:
            _schedule_retry(today)

    try:
        # 1. Notion 토큰 확인 (외부 호출 전)
        token = _load_notion_token()
        if not token:
            fail("Notion 토큰 없음 — work/api_keys.json 의 notion 키를 입력하세요.", schedule=False)
            return

        # 2. 멱등성 검사 — 오늘 페이지가 이미 있으면 브라우저 구동 없이 성공 처리
        title = f"Grok news_{today}"
        found = news_notion.find_today_report(NOTION_PARENT_PAGE_ID, token, title)
        if found:
            _log(f"오늘 페이지 이미 존재 — 스킵 ({title})")
            return

        # 3. 공유 브라우저 락 획득 (10분)
        if not browser_lock.acquire("grok", wait_sec=600):
            fail("브라우저 락 10분 미획득(리디 수집 진행 중으로 추정) — 잠시 후 재시도됩니다.")
            return

        report = None
        backup_path = None
        try:
            # 4. 잔여 Singleton 락 삭제
            _clear_singleton_locks()
            # 5. persistent context 구동
            with sync_playwright() as p:
                context = _new_grok_browser(p)
                try:
                    page = context.new_page()
                    # 6. 접속 + Cloudflare 대기
                    page.goto(GROK_URL, wait_until="domcontentloaded", timeout=60000)
                    if not _wait_cloudflare(page, 90):
                        fail("Cloudflare 90초 미통과 — 잠시 후 재시도됩니다.")
                        return
                    # 7. 로그인 판별
                    if not _is_logged_in(page):
                        if sys.stdin.isatty() and not HEADLESS:
                            # 맥 부트스트랩 — 사람이 있는 창에서만 수동 로그인 대기(함정 3)
                            _log("미로그인 감지 — 창에서 직접 로그인 후 Enter (맥 부트스트랩)")
                            try:
                                input("  로그인 완료 후 Enter > ")
                            except EOFError:
                                time.sleep(30)
                            if not _is_logged_in(page):
                                fail("로그인 후에도 입력창을 찾지 못함 — grok.com 화면 구조 변경 의심")
                                return
                        else:
                            fail("grok.com 세션 만료(미로그인) — 맥에서 grok_profile 재로그인 후 "
                                 "NAS grok_profile/ 에 복사해야 합니다.")
                            _log("무인 환경 + 미로그인 → 이번 실행 건너뜀")
                            return
                    # 8. 프롬프트 로드·치환·전송
                    _submit_prompt(page, _load_prompt(today))
                    # 9. 완료 감지
                    if not _wait_response_done(page):
                        fail("응답이 하드 타임아웃(20분) 내 미완 — 잠시 후 재시도됩니다.")
                        return
                    # 10. 응답 추출
                    text = _extract_report(page)
                    # 11. 품질 게이트
                    reason = _quality_gate(text)
                    if reason:
                        fail(f"응답 품질 미달({reason}) — 업로드하지 않고 재시도합니다.")
                        return
                    # 12. 원문 백업 저장 (Notion 실패 대비)
                    backup_path = os.path.join(OUTPUT_DIR, f"grok_news_{today}.md")
                    try:
                        with open(backup_path, "w", encoding="utf-8") as f:
                            f.write(text)
                        _log(f"원문 백업 저장 — {backup_path}")
                    except Exception as e:
                        _log(f"원문 백업 저장 실패(계속 진행) — {e}")
                    report = text
                finally:
                    # 13. 브라우저 닫기 (Notion 업로드 전에 — 2GB RAM 배려)
                    try:
                        context.close()
                    except Exception:
                        pass
        finally:
            browser_lock.release()

        if report is None:
            return   # 위 실패 경로에서 알림·재시도 이미 처리됨

        # 14. Notion 업로드
        try:
            blocks = news_notion.markdown_to_blocks(report)
            page_id = news_notion.create_report_page(
                NOTION_PARENT_PAGE_ID, token, title, blocks)
            _log(f"Notion 업로드 완료 — {news_notion.page_url(page_id)}")
        except Exception as e:
            _log("Notion 업로드 실패:\n" + traceback.format_exc())
            head = str(e).splitlines()[0] if str(e) else type(e).__name__
            fail(f"Notion 업로드 실패 — {head} (백업 파일: {backup_path})")
            return

        # 15. 성공 (성공 알림은 보내지 않음)

    except Exception as e:
        _log("run_grok_report 예외:\n" + traceback.format_exc())
        head = str(e).splitlines()[0] if str(e) else type(e).__name__
        fail(f"Grok 실행 중 예기치 못한 오류 — {head} (grok.com 화면 구조 변경 의심)")


# ── probe 스파이크(§5 0단계) — Notion 미호출 ──────────────────
def _screenshot(page, tag):
    path = os.path.join(OUTPUT_DIR, f"grok_probe_{tag}.png")
    try:
        page.screenshot(path=path, full_page=False)
        _log(f"스크린샷 저장 — {path}")
    except Exception as e:
        _log(f"스크린샷 실패({tag}) — {e}")


def probe() -> None:
    """셀렉터·완료 신호 실측 검증 전용. Notion 미호출, 단계별 스크린샷 저장."""
    _log("=== probe 모드 시작 (Notion 미호출) ===")
    if not browser_lock.acquire("grok", wait_sec=600):
        _log("브라우저 락 미획득 — probe 종료")
        return
    try:
        _clear_singleton_locks()
        with sync_playwright() as p:
            context = _new_grok_browser(p)
            try:
                page = context.new_page()
                page.goto(GROK_URL, wait_until="domcontentloaded", timeout=60000)
                _screenshot(page, "01_loaded")
                cf = _wait_cloudflare(page, 90)
                _log(f"Cloudflare 통과: {cf}")
                _screenshot(page, "02_after_cf")
                logged = _is_logged_in(page)
                _log(f"로그인 상태: {logged}")
                if not logged:
                    if sys.stdin.isatty() and not HEADLESS:
                        _log("미로그인 — 창에서 로그인 후 Enter (세션이 프로필에 저장됨)")
                        try:
                            input("  로그인 완료 후 Enter > ")
                        except EOFError:
                            time.sleep(30)
                        logged = _is_logged_in(page)
                        _log(f"로그인 후 재확인: {logged}")
                    else:
                        _log("무인 환경 + 미로그인 → probe 종료")
                        return
                _screenshot(page, "03_logged_in")
                # 짧은 테스트 프롬프트
                _submit_prompt(page, "한 문장으로만 답해줘. 오늘 날짜는?")
                _screenshot(page, "04_submitted")
                # 짧은 응답이라 마지막 섹션 조건은 끄고, 최소경과+안정화로만 완료 판정
                done = _wait_response_done(page, hard_timeout=300, require_last_section=False)
                _log(f"응답 완료 감지: {done}")
                text = _extract_report(page)
                _screenshot(page, "05_response")
                out = os.path.join(OUTPUT_DIR, "grok_probe_response.txt")
                try:
                    with open(out, "w", encoding="utf-8") as f:
                        f.write(text)
                    _log(f"probe 응답 저장 — {out} (길이 {len(text)})")
                except Exception as e:
                    _log(f"probe 응답 저장 실패 — {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    finally:
        browser_lock.release()


# ── 메인 루프 (20초 시계, 함정 8 준수 — >= 비교) ───────────────
def main() -> None:
    try:
        s = load_grok_settings()
        mode = "headless(창 없음)" if HEADLESS else "실제 창"
        _log(f"=== Grok 뉴스봇 시작 === daily_time={s['daily_time']} 브라우저={mode}")
    except Exception:
        _log("시작 초기화 오류:\n" + traceback.format_exc())

    while True:
        try:
            s = load_grok_settings()
            now = datetime.now()
            # ① retry_at 도달 시 재시도(재실패해도 추가 재시도 없음)
            rat = s.get("retry_at", "")
            if rat:
                try:
                    due = datetime.strptime(rat, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    due = None
                if due and now >= due:
                    s["retry_at"] = ""
                    save_grok_settings(s)
                    _log("retry_at 도달 — 재시도 실행(record_retry=False)")
                    run_grok_report(record_retry=False)
                    time.sleep(20)
                    continue
            # ② 정기 실행 — now >= daily_time 이고 오늘 미실행
            if now.strftime("%H:%M") >= s["daily_time"] and \
               s["last_run_date"] != now.strftime("%Y-%m-%d"):
                s["last_run_date"] = now.strftime("%Y-%m-%d")
                save_grok_settings(s)   # 시작 직후 기록 — 무한 재구동 방지(§3.1)
                _log("정기 실행 시각 도달 — 실행")
                run_grok_report(record_retry=True)
        except Exception:
            _log("메인 루프 오류:\n" + traceback.format_exc())
        time.sleep(20)


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
    elif "--once" in sys.argv:
        run_grok_report(record_retry=False)
    else:
        main()
