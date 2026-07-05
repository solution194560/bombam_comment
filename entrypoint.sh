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

exec "$@"
