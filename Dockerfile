# 저사양 컨테이너용 - 공식 python 이미지(데비안 slim) 사용
# ⚠️ python:*-alpine 은 사용 금지 (Playwright Chromium 미지원)
FROM python:3.12-slim

WORKDIR /app

# 1) 파이썬 패키지
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Chromium + 시스템 의존성(libnss3 등) + xvfb(가상 화면) 설치
#    xvfb 로 '진짜 창'처럼 띄워야 서버에서도 Cloudflare 통과가 잘 됩니다.
RUN python -m playwright install --with-deps chromium \
    && apt-get update && apt-get install -y --no-install-recommends xvfb xauth tzdata \
    && rm -rf /var/lib/apt/lists/*

# 시간대 한국 고정 (매일 11시 = 한국시간 기준이 되도록)
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/Asia/Seoul /etc/localtime && echo "Asia/Seoul" > /etc/timezone

# 3) 소스 복사
COPY . .
RUN chmod +x /app/entrypoint.sh

# 수집(크롬)은 '실제 창' 모드로 — 컨테이너 시작 시 entrypoint 가 Xvfb(:99)를 띄움
ENV HEADLESS=0
ENV DISPLAY=:99
# 로그인 쿠키 프로필 (로컬에서 만든 .browser_data_dir 를 이 경로로 복사/마운트)
ENV BROWSER_PROFILE=/app/.browser_data_dir
# Grok 전용 브라우저 프로필 (리디와 분리 — 세션 오염·Singleton 락 충돌 방지)
ENV GROK_PROFILE=/app/.grok_profile
# 결과물(엑셀/JSON)이 떨어질 폴더 → 볼륨 마운트해서 NAS로 빼냄
ENV OUTPUT_DIR=/app/out

# entrypoint: Xvfb 가상화면 시작 → DISPLAY 설정 → 봇 실행
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-u", "bot.py"]
