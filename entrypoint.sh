#!/usr/bin/env bash
# 컨테이너 시작 시 Xvfb 가상 화면을 띄우고 DISPLAY 를 설정한 뒤 봇 실행.
# (xvfb-run 래퍼는 일부 환경에서 hang 하므로 Xvfb 를 직접 구동)
set -e

# 이전 잔여 락 정리 (안전)
rm -f /tmp/.X99-lock 2>/dev/null || true

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99

# Xvfb 가 뜰 때까지 잠깐 대기
sleep 2

# AI 뉴스 리포트 봇 — 죽으면 30초 후 자동 재기동 (별도 상주 프로세스, 로그는 컨테이너 로그에 합류)
(
  while true; do
    python -u /app/news_bot.py || true
    echo "[news] 뉴스봇 프로세스 종료 감지 — 30초 후 재기동"
    sleep 30
  done
) &

# Grok 뉴스 보고서 봇 — 죽으면 30초 후 자동 재기동
(
  while true; do
    python -u /app/news_grok.py || true
    echo "[grok] Grok봇 프로세스 종료 감지 — 30초 후 재기동"
    sleep 30
  done
) &

exec "$@"
