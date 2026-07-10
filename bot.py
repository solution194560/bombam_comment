#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
항상 켜진 텔레그램 봇
────────────────────────────────────────────────────────────
역할
  1) 텔레그램 명령으로 설정(settings.json) 변경
  2) 매일 정해진 시간(daily_time)에 '오늘 기준 N일치 새 댓글' 수집 → 알림
실행
  python3 bot.py        (컨테이너에서 24시간 상주)
명령 (텔레그램에서 입력)
  /help            도움말
  /status          현재 설정·마지막 실행 보기
  /days N          며칠치 댓글을 볼지 (예: /days 3)
  /time HH:MM      매일 실행 시간 (예: /time 11:00)
  /empty on|off    새 댓글 없을 때도 알림 보낼지
  /author 이름 URL 작가 변경 (URL=작가 페이지 주소)
  /run             지금 즉시 한 번 수집·알림
────────────────────────────────────────────────────────────
"""
import os
import sys
import json
import time
import threading
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import ridi_collector as rc
import browser_lock
from notify import _load_telegram

HERE = os.path.dirname(os.path.abspath(__file__))
POLL_TIMEOUT = 50          # 롱폴링 대기(초)
_job_running = threading.Event()   # 수집 작업 진행 중 표시 (중복 실행 방지)


# ── 텔레그램 통신 ─────────────────────────────────────
def _api(method, params=None, timeout=60):
    cfg = _load_telegram()
    if not cfg["bot_token"]:
        return None
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [api] {method} 오류: {e}")
        return None


def send(chat_id, text):
    res = _api("sendMessage", {"chat_id": chat_id, "text": text,
                               "disable_web_page_preview": "true"}, timeout=15)
    return bool(res and res.get("ok"))


# ── 명령 처리 ─────────────────────────────────────────
HELP = (
    "🤖 봄밤 알림봇 명령\n"
    "/status  현재 설정 보기\n"
    "/days N  며칠치 댓글 (예: /days 3)\n"
    "/time HH:MM  매일 시간 (예: /time 11:00)\n"
    "/empty on|off  빈 날도 알림\n"
    "/author 이름 URL  작가 변경\n"
    "/run  지금 즉시 수집·알림"
)


def status_text():
    s = rc.load_settings()
    return (f"⚙️ 현재 설정\n"
            f"작가: {s['author']}\n"
            f"매일 시간: {s['daily_time']}\n"
            f"댓글 일수: 최근 {s['notify_days']}일\n"
            f"빈 날 알림: {'예' if s['notify_when_empty'] else '아니오'}\n"
            f"마지막 실행: {s['last_run_date'] or '(없음)'}\n"
            f"매일 알림 받는 사람: {len(s.get('subscribers') or [])}명\n"
            f"상태: {'🔄 수집 진행 중' if _job_running.is_set() else '✅ 대기 중'}")


def handle_command(text, chat_id):
    parts = text.strip().split()
    cmd = parts[0].lower()
    s = rc.load_settings()

    if cmd in ("/help", "/start"):
        send(chat_id, HELP)
    elif cmd == "/status":
        send(chat_id, status_text())
    elif cmd == "/days":
        if len(parts) >= 2 and parts[1].isdigit():
            s["notify_days"] = int(parts[1]); rc.save_settings(s)
            send(chat_id, f"✅ 댓글 일수 → 최근 {parts[1]}일")
        else:
            send(chat_id, "사용법: /days 3")
    elif cmd == "/time":
        if len(parts) >= 2 and _valid_time(parts[1]):
            s["daily_time"] = parts[1]; rc.save_settings(s)
            send(chat_id, f"✅ 매일 시간 → {parts[1]}")
        else:
            send(chat_id, "사용법: /time 11:00")
    elif cmd == "/empty":
        if len(parts) >= 2 and parts[1].lower() in ("on", "off"):
            s["notify_when_empty"] = (parts[1].lower() == "on"); rc.save_settings(s)
            send(chat_id, f"✅ 빈 날 알림 → {'켜짐' if s['notify_when_empty'] else '꺼짐'}")
        else:
            send(chat_id, "사용법: /empty on  또는  /empty off")
    elif cmd == "/author":
        if len(parts) >= 3:
            s["author"] = parts[1]; s["author_url"] = parts[2]; rc.save_settings(s)
            send(chat_id, f"✅ 작가 → {parts[1]}\nURL → {parts[2]}\n(다음 실행부터 적용)")
        else:
            send(chat_id, "사용법: /author 작가이름 작가페이지URL")
    elif cmd == "/run":
        start_job(triggered_by=chat_id)
    else:
        send(chat_id, "❓ 모르는 명령. /help 참고")


def _register_subscriber(chat_id):
    """봇에게 말을 건 사람을 매일 자동 알림 구독자로 등록(중복 없이)."""
    s = rc.load_settings()
    subs = list(s.get("subscribers") or [])
    if chat_id not in subs:
        subs.append(chat_id)
        s["subscribers"] = subs
        rc.save_settings(s)


def _valid_time(t):
    try:
        datetime.strptime(t, "%H:%M"); return True
    except ValueError:
        return False


# ── 매일 작업 실행 (백그라운드 스레드 → 봇은 계속 명령 응답) ──
def start_job(triggered_by=None, is_auto=False):
    """수집 작업을 백그라운드 스레드로 시작 (이미 실행 중이면 거절).
       is_auto=True 는 매일 정기 알림(자동). False 는 /run(수동)."""
    owner = _load_telegram()["chat_id"]
    target = triggered_by or owner
    if _job_running.is_set():
        if target:
            send(target, "⏳ 이미 수집이 진행 중이에요. 끝나면 결과가 옵니다.")
        return
    if target:
        send(target, "▶️ 수집 시작! 끝나면 결과를 보낼게요. (몇 분~)")
    threading.Thread(target=run_daily_job, args=(target, is_auto), daemon=True).start()


def run_daily_job(triggered_by=None, is_auto=False):
    """4_매일알림.py 를 새 프로세스로 실행 (설정을 새로 읽어 작가/일수 반영).
       크롬은 '실제 창' 모드(HEADLESS=0). 컨테이너에선 entrypoint 의 Xvfb(:99),
       맥에선 실제 화면을 사용 (DISPLAY 는 환경에서 상속)."""
    _job_running.set()
    # Grok 봇과 브라우저 동시 구동 방지(2GB RAM OOM 차단). 리디는 주 기능이므로 대기 초과 시 강행.
    got_lock = browser_lock.acquire("ridi", wait_sec=1500)   # Grok 최장 20분 + 여유 = 25분 대기
    if not got_lock:
        print("[락] 25분 대기에도 브라우저 락 미해제 — 리디가 주 기능이므로 강행", flush=True)
    cmd = [sys.executable, os.path.join(HERE, "4_매일알림.py")]
    env = dict(os.environ); env.setdefault("HEADLESS", "0")
    # 결과 알림 수신자.
    #  · 매일 자동 실행(is_auto) → 플래그만 넘기고, 실제 수신자 목록은
    #    4_매일알림.py 가 '발송 직전에' settings.json 에서 새로 읽는다.
    #    (수집이 도는 몇 분 사이에 등록한 사람도 그날 알림을 받도록)
    #  · /run 을 누른 사람(수동) → 그 사람에게만
    if is_auto:
        env["TELEGRAM_AUTO"] = "1"
    elif triggered_by:
        env["TELEGRAM_CHAT_ID"] = str(triggered_by)
    try:
        subprocess.run(cmd, cwd=HERE, env=env, timeout=3600)
    except Exception as e:
        if triggered_by:
            send(triggered_by, f"⚠️ 실행 오류: {str(e)[:80]}")
    finally:
        # 매일 정기 알림(자동)만 '오늘 실행함'으로 기록 → 하루 한 번만 자동 발송.
        # 수동 /run 은 기록하지 않음(테스트로 /run 해도 그날 정기 알림이 막히지 않도록).
        if is_auto:
            s = rc.load_settings(); s["last_run_date"] = datetime.now().strftime("%Y-%m-%d")
            rc.save_settings(s)
        if got_lock:
            browser_lock.release()
        _job_running.clear()


# ── 메인 루프 ─────────────────────────────────────────
def main():
    print("=== bombam bot 컨테이너 시작 ===", flush=True)
    print(f"  OUTPUT_DIR={os.environ.get('OUTPUT_DIR')} HEADLESS={os.environ.get('HEADLESS')} "
          f"DISPLAY={os.environ.get('DISPLAY')}", flush=True)
    print(f"  현재 컨테이너 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
          f"(한국시간이어야 정상 / 매일 {rc.load_settings()['daily_time']} 에 자동 알림)", flush=True)
    cfg = _load_telegram()
    if not (cfg["bot_token"] and cfg["chat_id"]):
        print("❌ telegram.json 의 bot_token/chat_id 가 필요합니다.", flush=True)
        return
    owner = str(cfg["chat_id"])
    _register_subscriber(owner)   # 소유자는 항상 매일 자동 알림 구독자
    print("🤖 봄밤 알림봇 시작. (Ctrl+C 종료)", flush=True)
    if not send(owner, "🤖 봄밤 알림봇 가동 시작!\n" + HELP):
        print("⚠️ 시작 메시지 전송 실패 (네트워크/토큰 확인). 계속 폴링은 시도합니다.", flush=True)

    offset = None
    failure_count = 0     # getUpdates 연속 실패 횟수
    max_backoff = 60      # 지수 백오프 상한(초)
    log_throttle = 0      # 로그 도배 방지용 카운터
    while True:
        # [재시도 확인] settings.json의 retry_at이 지났으면 자동 실행
        try:
            s = rc.load_settings()
            retry_at_str = s.get("retry_at", "")
            if retry_at_str:
                retry_at = datetime.strptime(retry_at_str, "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                if now >= retry_at and not _job_running.is_set():
                    print(f"[자동 재시도] 이전 조기 중단 후 {(now - retry_at).total_seconds():.0f}초 경과, 다시 수집 실행", flush=True)
                    # 재시도는 자동(is_auto=True) 아님 → 실패 알림만 전송되고 success 알림은 정상 흐름
                    run_daily_job(is_auto=False)
                    # 재시도 완료 후 플래그 제거 (다시 설정되지 않는 한 재실행 안 함)
                    s.pop("retry_at", None)
                    rc.save_settings(s)
        except Exception as e:
            print(f"  [재시도 확인 오류] {str(e)[:60]}", flush=True)

        # 1) 명령 수신 (롱폴링)
        params = {"timeout": POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        res = _api("getUpdates", params, timeout=POLL_TIMEOUT + 10)
        if res and res.get("ok"):
            # 정상 복구 시 실패 카운터 초기화
            if failure_count > 0:
                print(f"getUpdates 정상 복구 (실패 {failure_count}회 후)", flush=True)
            failure_count = 0
            log_throttle = 0
            for upd in res["result"]:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat_id = str((msg.get("chat") or {}).get("id", ""))
                text = msg.get("text", "")
                if not text:
                    continue
                # (누구나 사용 가능 — 소유자 전용 차단 없음)
                # ※ 설정(settings.json)은 모두가 공유하므로 /days, /author 등
                #    설정 변경은 소유자 포함 전원에게 적용됨.
                # 봇에게 말 건 사람은 매일 자동 알림 구독자로 자동 등록됨.
                _register_subscriber(chat_id)
                if text.startswith("/"):
                    handle_command(text, chat_id)
                else:
                    send(chat_id, "명령은 / 로 시작해요. /help")
        else:
            # getUpdates 실패(네트워크 장애 등) → 지수 백오프로 재시도 간격을 늘린다.
            #  1초 → 2초 → 4초 → 8초 → … → 60초 상한
            failure_count += 1
            backoff = min(2 ** (failure_count - 1), max_backoff)
            # 로그 도배 방지: 첫 실패와 매 10회마다만 출력
            log_throttle += 1
            if failure_count == 1 or log_throttle % 10 == 0:
                print(f"[getUpdates 실패 {failure_count}회] {backoff}초 대기 후 재시도...", flush=True)
            time.sleep(backoff)
            continue

        # 2) 매일 정해진 시간 도달 시 자동 실행.
        #    == 대신 >= : 롱폴링(최대 50초)으로 정확한 1분을 놓쳐도 그 시각 이후 실행됨.
        #    하루 한 번만: last_run_date != 오늘 조건으로 방지.
        s = rc.load_settings()
        now = datetime.now()
        if now.strftime("%H:%M") >= s["daily_time"] and \
           s["last_run_date"] != now.strftime("%Y-%m-%d") and not _job_running.is_set():
            print(f"⏰ {s['daily_time']} 도달 → 자동 수집 실행 (현재 {now.strftime('%H:%M')})", flush=True)
            start_job(is_auto=True)

        time.sleep(1)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("❌ 봇 비정상 종료:\n" + traceback.format_exc(), flush=True)
        raise
