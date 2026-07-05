#!/usr/bin/env bash
# 우분투/컨테이너 1회 설치 스크립트
set -e

echo "[1/4] 파이썬 패키지 설치"
pip3 install -r requirements.txt

echo "[2/4] Chromium + 시스템 의존성 설치"
# 루트 권한이 있으면 --with-deps 가 필요한 라이브러리(libnss3 등)까지 깔아줌
python3 -m playwright install --with-deps chromium || python3 -m playwright install chromium

echo "[3/4] (저메모리용) /dev/shm 부족 대비 안내"
echo "   docker 실행 시  --shm-size=1g  또는  --ipc=host  권장"

echo "[4/4] 완료. 사용법:"
echo "   화면 없는 서버:  HEADLESS=1 python3 2_작품별_최신댓글.py"
echo "   (성인 콘텐츠는 로그인 쿠키 필요 → README_컨테이너.md 참고)"
