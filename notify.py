#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
텔레그램 알림 전송 모듈
  · telegram.json 의 bot_token / chat_id 사용 (환경변수 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 우선)
  · 외부 패키지 없이 표준 라이브러리(urllib)만 사용
"""
import os
import json
import urllib.parse
import urllib.request

TELEGRAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram.json")


def _load_telegram():
    cfg = {"bot_token": "", "chat_id": ""}
    if os.path.exists(TELEGRAM_FILE):
        try:
            data = json.load(open(TELEGRAM_FILE, encoding="utf-8"))
            cfg["bot_token"] = str(data.get("bot_token", "") or "")
            cfg["chat_id"] = str(data.get("chat_id", "") or "")
        except Exception as e:
            print(f"  [텔레그램] {os.path.basename(TELEGRAM_FILE)} 읽기 실패: {e}")
    cfg["bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN", cfg["bot_token"])
    cfg["chat_id"] = os.environ.get("TELEGRAM_CHAT_ID", cfg["chat_id"])
    return cfg


def notify_telegram(text: str, chat_id: str = None) -> bool:
    """텔레그램으로 메시지 1건 전송. chat_id 를 주면 그 사람에게, 없으면 기본 설정으로.
       성공하면 True."""
    cfg = _load_telegram()
    target = chat_id or cfg["chat_id"]
    if not (cfg["bot_token"] and target):
        print("  [텔레그램] 토큰/챗ID 미설정 → 전송 생략")
        return False
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": target,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as r:
            res = json.loads(r.read().decode())
        if res.get("ok"):
            return True
        print(f"  [텔레그램] 전송 실패: {res}")
        return False
    except Exception as e:
        print(f"  [텔레그램] 전송 오류: {e}")
        return False


if __name__ == "__main__":
    # 단독 실행 시 연결 테스트
    print("전송 성공" if notify_telegram("🔔 봄밤 알림봇 테스트") else "전송 실패")
