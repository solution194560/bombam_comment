# 봄밤 텔레그램 알림봇 프로젝트 — 인수인계 문서

(다른 LLM/세션에서 이어받을 수 있도록 작성한 전체 요약. 2026-07-01 기준)

## 1. 목표

리디북스(성인 웹소설 플랫폼) 작가 "봄밤"(author_url: `https://ridibooks.com/author/117346`)의
작품·댓글을 Playwright로 스크래핑해서, 매일 정해진 시각에 "최근 N일 새 댓글"을 텔레그램으로
알려주는 시스템. 설정(작가/시간/일수/빈날알림)은 텔레그램 명령으로 실시간 변경 가능.
최종 목표는 **시놀로지 NAS(DS224+, Intel Celeron J4125, RAM 2GB)에서 Docker 컨테이너로
24시간 상주 운영**하는 것.

작업 폴더: `/Users/hyundeok/Downloads/봄밤작가 작품 리스트와 댓글 평가-3/`

사용자는 시놀로지/DSM/Docker/git 등 개발 도구 경험이 거의 없는 초보자. 안내 시 메뉴명·클릭
순서까지 구체적으로 설명해야 함. SSH가 막혀서 GUI(File Station + Container Manager) 위주로
작업해왔음.

## 2. 핵심 파일 구성

| 파일 | 역할 |
|---|---|
| `ridi_collector.py` | 수집 엔진 — 로그인, Cloudflare 대기, 스크래핑, 엑셀 생성, 설정 로드 |
| `bot.py` | 24시간 상주 텔레그램 봇. 명령: `/status /days /time /empty /author /run /help` |
| `notify.py` | 텔레그램 전송 전용 (urllib만 사용, 외부 의존성 없음) |
| `settings.json` | `author`, `daily_time`(기본 11:00), `notify_days`(기본 2), `notify_when_empty`(false), `last_run_date` — 봇이 텔레그램 명령으로 직접 수정 |
| `account.json` | 리디북스 로그인 계정 (id: solution11) |
| `telegram.json` | 텔레그램 봇 토큰 + `chat_id`(276954538, 소유자 전용 — 이 chat_id 외 명령은 봇이 거부) |
| `entrypoint.sh` | 컨테이너 시작 스크립트 — Xvfb(:99)를 직접 띄우고 `DISPLAY` export 후 `exec "$@"` |
| `Dockerfile` | `python:3.12-slim` 기반, Playwright+Chromium, xvfb, `TZ=Asia/Seoul` 고정 |
| `docker-compose.yml` | NAS Container Manager용 배포 설정 (아래 5번 참고) |
| `bombam_synology.zip` | NAS 업로드용 최종 배포 묶음 (22개 파일, 수정 후 매번 재생성) |
| `1_전체수집.py` / `2_작품별_최신댓글.py` / `3_최근30일_댓글.py` / `4_매일알림.py` | 단독 실행 스크립트들. `bot.py`는 `/run` 시 `4_매일알림.py`를 서브프로세스로 실행 |
| `requirements.txt` | `playwright>=1.40`, `pandas>=2.0`, `openpyxl>=3.1` |

## 3. 지금까지 해결한 주요 이슈 (원인까지 — 재발 시 참고)

1. **작품 제목이 "상세페이지 바로가기"로 수집됨** — 비로그인 상태로 작가 페이지를 긁으면
   링크 텍스트만 잡힘. → 각 책 상세페이지의 `og:title`(TITLE_JS)로 보정하는 로직을 모든
   수집 함수에 적용해 해결.
2. **NAS의 headless 크롬이 Cloudflare에 막힘** — 서버 IP + headless 조합은 봇으로 감지됨.
   → Xvfb 가상 화면으로 "진짜 창"처럼 띄우는 방식으로 우회.
3. **`xvfb-run` 래퍼가 이 환경에서 무한 hang** (중요, 재발 가능) — `xvfb-run -a python ...`
   자체가 안 끝남. → `entrypoint.sh`에서 `Xvfb :99 &`로 직접 띄우고 `DISPLAY=:99` export 후
   `exec "$@"` 하는 방식으로 교체해서 해결.
4. **컨테이너 시간대가 UTC** — "매일 11시"가 실제로는 다른 시각에 실행될 뻔함. →
   `ENV TZ=Asia/Seoul` + `/etc/localtime` 심볼릭 링크로 고정.
5. **시놀로지에서 단일 json 파일을 볼륨 마운트하면 컨테이너 시작 자체가 실패**(로그도 안 남음)
   — 호스트에 파일이 없으면 Docker가 동명의 빈 "폴더"를 만들어버림. → account.json /
   telegram.json / settings.json은 **이미지 안에 복사되는 것만 사용**하고 볼륨 마운트하지 않음
   (폴더만 마운트: `profile/`, `work/`).
6. **빈 작품목록([])이 저장되면 계속 "0개 사용"으로 캐시되어 굳음** — Cloudflare가 막혔을 때
   빈 목록이 저장된 게 원인. → `_load_or_collect_works()`: 0개면 동봉된 시드 목록 사용 →
   그래도 없으면 재수집, 빈 목록은 저장하지 않음.
7. **2GB RAM NAS에서 `mem_limit: 1500m` 설정 시 Chromium 순간 사용량 초과로 OOM 강제종료
   (재시작 반복) 의심** → docker-compose에서 `mem_limit` 제거.

## 4. 로컬 Docker 검증 이력

### 1차 검증 (이전 세션, 성공)
맥에 Docker Desktop 설치 후 컨테이너로 전체 파이프라인 실증: Xvfb 실제 창 모드로 Cloudflare
통과 → account.json 아이디/비번으로 **자동 로그인 성공**(쿠키 복사 불필요임을 확인) →
작품목록 31개 정상 수집 → 텔레그램 알림 실제 발송 성공.

### 2차 검증 (오늘, 2026-07-01, 진행 중 — 막힘)
1차 검증 이후 Dockerfile/entrypoint.sh/bot.py/ridi_collector.py 등이 추가 수정됨
(당일 새벽 02:40~03:36 사이). 최신 코드 반영 확인을 위해 재검증 시작:

1. 기존에 떠 있던 옛날 컨테이너(`musing_nash`, 10시간 전 생성, 옛날 `xvfb-run` 방식) 발견 →
   중지·삭제.
2. `docker build -t bombam:test .` 로 최신 코드 재빌드 → **성공**.
3. `docker run` 으로 로컬 테스트 볼륨(`./local_test/profile`, `./local_test/work`)을 붙여
   기동 → 컨테이너/Xvfb/봇 프로세스는 정상 기동 확인.
4. **막힘**: 봇이 텔레그램 `getUpdates` 호출 시 계속 `HTTP Error 409: Conflict` 발생.
   - 텔레그램 API는 봇 토큰 하나당 동시에 하나의 polling(getUpdates)만 허용함.
   - Mac 로컬에 다른 python/bombam 프로세스, 다른 docker 컨테이너 없음을 확인함.
   - 컨테이너 내부에도 `bot.py` 프로세스 1개 + `Xvfb` 1개만 있음을 `/proc` 확인으로 검증함
     (자체 중복 실행 아님).
   - `getWebhookInfo` 확인 결과 webhook 없음(url 빈 문자열, `pending_update_count: 0`) —
     즉 실시간으로 누군가 업데이트를 다 받아가고 있다는 뜻.
   - 컨테이너를 완전히 멈춘 상태에서 `curl .../getUpdates`는 정상 응답(빈 결과)이 나온 적도
     있었지만, 컨테이너를 다시 켜면 즉시 다시 409가 재현됨 — 재현성 있는 충돌.
   - 컨테이너가 혼자 떠 있는 상태(다른 curl 호출 없이)에서도 70초간 지켜본 결과 여러 차례
     빠르게(짧은 간격으로) 409가 반복됨 — 정상적인 롱폴링 타임아웃(50초)보다 훨씬 빠르게
     실패하는 패턴이라, **어딘가 외부에서 같은 토큰으로 실제로 폴링 중인 다른 프로세스가
     있다는 강한 정황**.
   - 사용자에게 NAS의 Container Manager에서 `bombam` 컨테이너가 실행 중인지 확인 요청 →
     사용자가 "지금 껐어"라고 답했지만, 그 이후에도 충돌이 계속 재현됨(끄기 전/후 판단이
     명확치 않은 상태).
   - **원인이 100% 확정되지 않음.** 유력 용의자는 NAS에 이미 떠 있는(혹은
     `restart: unless-stopped` 정책으로 재부팅 시 자동 재시작된) 예전 봄밤 컨테이너지만,
     직접 DSM에 들어가 확인하지 못해 확증은 안 됨.
   - 해결책으로 "임시 테스트용 봇 토큰(BotFather로 새로 발급)을 만들어 로컬 검증만 따로
     진행"을 제안했으나, 사용자가 이 단계에서 **일단 중지**를 요청함 (현재 상태).

## 5. 현재 파일 상태 스냅샷

### Dockerfile (핵심 부분)
```
FROM python:3.12-slim
...
RUN python -m playwright install --with-deps chromium \
    && apt-get update && apt-get install -y --no-install-recommends xvfb xauth tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/Asia/Seoul /etc/localtime && echo "Asia/Seoul" > /etc/timezone
COPY . .
RUN chmod +x /app/entrypoint.sh
ENV HEADLESS=0
ENV DISPLAY=:99
ENV BROWSER_PROFILE=/app/.browser_data_dir
ENV OUTPUT_DIR=/app/out
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-u", "bot.py"]
```

### entrypoint.sh
```bash
#!/usr/bin/env bash
set -e
rm -f /tmp/.X99-lock 2>/dev/null || true
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99
sleep 2
exec "$@"
```

### docker-compose.yml (NAS 배포용, Container Manager 프로젝트로 등록)
```yaml
services:
  bombam:
    build: .
    image: bombam:latest
    container_name: bombam
    shm_size: "1gb"
    environment:
      - HEADLESS=1
      - BROWSER_PROFILE=/app/.browser_data_dir
      - PYTHONUNBUFFERED=1
    volumes:
      - /volume1/docker/bombam/profile:/app/.browser_data_dir
      - /volume1/docker/bombam/work:/app/out
    restart: unless-stopped
    # mem_limit 는 의도적으로 두지 않음 (OOM 재시작 반복 이슈, 위 4번 항목 참고)
```

## 6. 지금 당장 필요한 다음 액션 (우선순위 순)

1. **텔레그램 409 Conflict 원인 확정**: 사용자가 직접 DSM → Container Manager → 컨테이너
   탭에서 `bombam` 컨테이너 상태(실행 중/중지됨)를 눈으로 확인하고 알려줘야 함. 실행 중이면
   완전히 정지시킨 뒤 로컬 테스트 재개.
2. (선택) 원인 확정이 오래 걸리면, BotFather로 임시 테스트용 봇 토큰을 새로 발급받아
   `telegram.json`을 로컬 테스트 전용 사본으로 바꿔서 NAS와 완전히 분리해 검증하는 방법도
   가능 (실제 배포용 토큰/설정은 그대로 둠).
3. 409 문제 해결 후: 로컬 컨테이너에서 `/run` 명령으로 실제 수집→알림 전체 파이프라인
   재검증 (로그인, Cloudflare 통과, 작품목록, 댓글 수집, 텔레그램 전송까지).
4. 로컬 검증 완료되면: 최신 `bombam_synology.zip` 재생성 → NAS의 `docker/bombam` 폴더에
   업로드해 압축 풀기(덮어쓰기) → Container Manager에서 재빌드 → 텔레그램 가동 메시지 확인
   → `/run`으로 NAS에서도 실동작 검증.

## 7. 협업 시 유의사항 (사용자 피드백 기반)

- 추측으로 원격(NAS) 환경을 고치려 하지 말고, 가능하면 로컬 Docker로 먼저 재현·검증할 것.
  (과거 이 방식으로 `xvfb-run` hang 원인을 실제로 찾아낸 전례 있음.)
- 시놀로지/NAS 설명은 전문용어 앞에 한 줄 정의 → 그 다음 클릭 단위 절차로 설명할 것.
- SSH가 막히면 바로 GUI(File Station + Container Manager) 대안으로 전환할 것 — 이 사용자
  환경에서는 SSH 터미널 접속이 안 됨("teletype 터미널이 없습니다" 오류).

---
*이 문서는 세션 간 인수인계용으로 작성됨. 최신 상태는 실제 파일(Dockerfile, bot.py,
ridi_collector.py 등)과 `docker ps -a` 결과를 기준으로 다시 확인할 것 — 이 문서는 작성
시점(2026-07-01) 스냅샷.*
