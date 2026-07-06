# 봄밤 텔레그램 알림봇 프로젝트

리디북스 작가 "봄밤"(author_url: `https://ridibooks.com/author/117346`)의 작품·댓글을
Playwright로 스크래핑해서, 매일 정해진 시각에 최근 N일 새 댓글을 텔레그램으로 알려주는 시스템.
시놀로지 NAS(DS224+, Celeron J4125, RAM 2GB)에서 Docker 컨테이너로 24시간 상주 운영.

## 작업 워크플로우 (반드시 준수)

**모든 코드/설정 변경은 이 순서로 진행한다:**
1. **작업 전 리뷰** — 무엇을, 왜 바꾸는지 먼저 설명하고 사용자 확인을 받는다.
2. **로컬 Docker 테스트** — `docker build` + `docker run`으로 실제 컨테이너에서 해당 시나리오를
   통과시킨다. 절대 추측만으로 NAS를 고치려 하지 않는다.
3. **통과했을 때만** `bombam_synology.zip`을 재생성해 시놀로지 배포로 넘어간다.

로컬 검증을 건너뛰고 바로 NAS 배포를 제안하지 않는다. (사용자가 명시적으로 요청한 규칙,
2026-07-02)

사용자는 시놀로지/Docker/개발도구 경험이 거의 없는 초보자. 안내 시 메뉴명·클릭 순서까지
구체적으로 설명할 것. SSH가 막혀 있어 GUI(File Station + Container Manager)로만 작업 가능.

## 코딩 행동 수칙

- **최소 구현** — 요청 범위 밖 기능·추상화·설정 옵션을 만들지 않는다. 2GB RAM NAS다.
- **수술적 수정** — 요청과 무관한 인접 코드·주석·포맷을 건드리지 않는다. 내 변경으로
  생긴 고아(import 등)만 정리한다.
- **에러는 원문으로** — 로그·스택트레이스 원문을 확인한 뒤 수정한다. 키워드 추측 금지.
- **커밋 제안** — 한 문장으로 설명되는 논리 단위가 완성되면 커밋을 제안한다(임의 커밋 금지).
- **한국어 출력 규칙** — 문장을 콜론(:)으로 끝내지 않는다. 새 소스 파일 첫 줄에는
  역할을 설명하는 한국어 주석 한 줄을 단다(설정 파일 제외).

## 개발 파이프라인 (다중 모델)

구조적 변경은 슬래시 커맨드로 자동화된 파이프라인을 쓴다(에이전트 정의는 `.claude/agents/`).
- **`/dev-pipeline <요구사항>`** — 설계(Fable)→검토(Codex)→최종설계(Fable)→구현(Opus)→테스트(Codex)→판정(Fable).
  - **경량 모드**(파일 1~2개·스키마 변경 없음): 검토·최종설계 생략, `01_설계.md`를 스펙으로 구현.
  - **정식 모드**(구조/다중 파일/스키마 변경): 전 단계 수행.
  - 판정은 항상 `pipeline-judge`(Fable) 고정 — 세션 모델이 직접 판정하지 않음.
  - 구현 직전 사용자 확인 게이트는 두 모드 모두 필수(위 "작업 전 리뷰" 규칙).
- **`/fix-error`** — 분석(Fable)→사용자 확인→구현(Opus)→테스트(Codex). NAS/로컬 에러 공용.
- 산출물은 `docs/설계/YYYYMMDD_<슬러그>/`에 `01_설계.md`~`05_에러분석.md`로 저장.

## 핵심 파일

| 파일 | 역할 |
|---|---|
| `ridi_collector.py` | 수집 엔진 — 로그인, Cloudflare 대기, 스크래핑(댓글+평점), 엑셀 생성, 설정 로드 |
| `bot.py` | 24시간 상주 텔레그램 봇. 명령: `/status /days /time /empty /author /run /help` |
| `notify.py` | 텔레그램 전송 (urllib만 사용). `TELEGRAM_CHAT_ID` 환경변수가 telegram.json보다 우선 |
| `settings.json` | author/daily_time/notify_days/notify_when_empty/last_run_date/retry_at/subscribers — 봇이 직접 수정 |
| `account.json` | 리디북스 로그인 계정 (id: solution11) |
| `telegram.json` | 텔레그램 봇 토큰 + chat_id(276954538, 소유자) |
| `entrypoint.sh` | 컨테이너 시작 — Xvfb(:99) 직접 구동 후 봇 실행 (`xvfb-run` 래퍼 금지) |
| `Dockerfile` / `docker-compose.yml` | python:3.12-slim, TZ=Asia/Seoul, **HEADLESS=0 필수** |
| `bombam_synology.zip` | NAS 업로드용 배포 묶음 (수정 후 매번 재생성) |
| `local_test/profile`, `local_test/work` | 로컬 Docker 테스트용 볼륨 마운트 폴더 |

## 알고 있어야 할 함정들 (재발 방지)

1. **`HEADLESS=1`(창 없음)로 두면 NAS에서 Cloudflare에 막혀 로그인 실패.** Xvfb 가상화면에
   '진짜 창'으로 띄워야 통과함 → `docker-compose.yml`/실행 시 반드시 `HEADLESS=0`.
2. **`xvfb-run -a python ...` 래퍼는 이 환경에서 무한 hang.** `entrypoint.sh`에서
   `Xvfb :99 &` 직접 띄우고 `DISPLAY=:99` export 후 `exec "$@"` 하는 방식만 사용.
3. **무인 컨테이너에서 자동 로그인 실패 시 `input()`으로 멈추면 안 됨.**
   `ridi_collector.py`의 `_try_login()`은 `sys.stdin.isatty()`일 때만(사람 있는 터미널)
   수동 로그인 대기, 아니면 "이번 실행 건너뜀"으로 처리.
4. **연속 실행 시 두 번째 로그인 실패 → 원인은 Chromium 프로필의 잔여 `Singleton*` 락.**
   재현되면 profile 폴더의 SingletonLock/SingletonCookie/SingletonSocket 삭제.
5. **시놀로지에서 단일 파일을 볼륨 마운트하면 컨테이너가 시작조차 안 됨**(로그도 없음).
   account.json/telegram.json/settings.json은 이미지에 COPY된 것만 쓰고, '폴더'만
   마운트(`profile/`, `work/`).
6. **빈 작품목록([])이 저장되면 "0개"로 캐시가 굳음.** `_load_or_collect_works()`는 0개면
   동봉 시드 목록 → 그래도 없으면 재수집, 빈 목록은 저장 안 함.
7. **2GB RAM NAS에서 `mem_limit` 설정 시 OOM 반복 재시작 의심** → docker-compose에 mem_limit
   두지 않음.
8. **매일 정기 자동 알림 로직**: 자동 실행만 `last_run_date`를 기록(수동 `/run`은 기록 안 함,
   테스트가 정기 알림을 막지 않도록). 시각 비교는 `==`가 아니라 `>=`(롱폴링으로 정확한 1분을
   놓쳐도 그 이후 실행됨).
9. **알림 수신자 규칙.** `/run`(수동) 결과는 누른 사람 **한 명**에게만 간다(`bot.py`가
   `TELEGRAM_CHAT_ID`로 `triggered_by`를 넘기고 notify.py가 telegram.json보다 우선 사용).
   매일 자동 알림(`is_auto`)은 `settings.json`의 `subscribers` **전원 + 소유자**에게 간다.
   subscribers는 봇에게 말 건 사람이 자동 등록되며 소유자는 항상 포함.
10. **구매자 평점(별점) 판별은 클래스명이 아니라 색으로.** 리뷰 li 안 `viewBox="0 0 48 48"`
    svg 중 색이 회색(`rgb(230,230,230)`)이 아니면 채워진 별. 클래스명은 CSS-in-JS 해시라
    매 빌드마다 바뀌므로 절대 의존하지 말 것.
11. **네트워크 장애·조기 중단 복원력.** `getUpdates` 실패 시 봇은 지수 백오프로 재시도
    (1→2→4→…→60초 상한, 로그는 첫 실패+10회마다만). 수집이 조기 중단되면 `settings.json`에
    `retry_at`(재시도 시각)을 기록하고, 그 시각이 지나면 봇이 자동으로 한 번 재수집한다
    (재시도는 `is_auto=False` — 성공 시 정상 알림, 실패 시 실패 알림).

## 로컬 테스트 실행법

```bash
cd "/Users/hyundeok/Downloads/봄밤작가 작품 리스트와 댓글 평가-3/"
docker stop bombam_test 2>&1; docker rm bombam_test 2>&1   # 기존 컨테이너 정리
rm -f local_test/profile/Singleton*                          # 잔여 락 정리
docker build -t bombam:test .
docker run -d --name bombam_test --shm-size=1gb \
  -e HEADLESS=0 \
  -v "$(pwd)/local_test/profile:/app/.browser_data_dir" \
  -v "$(pwd)/local_test/work:/app/out" \
  bombam:test
docker logs -f bombam_test          # 실시간 로그 확인
```

⚠️ **로컬 테스트 컨테이너와 NAS의 bombam 컨테이너는 같은 텔레그램 봇 토큰을 쓴다.** 둘 다
동시에 폴링하면 `409 Conflict`가 남. 로컬 테스트 전엔 NAS 쪽을, NAS 배포 전엔 로컬 컨테이너를
반드시 정리할 것.

## 시놀로지 배포 절차

1. File Station → `docker/bombam` 폴더 → `bombam_synology.zip` 덮어쓰기 업로드 → 압축 풀기(덮어쓰기)
2. Container Manager → 프로젝트 → `bombam` → **다시 빌드** (설정 변경 시 재시작만으론 반영 안 됨)
3. 텔레그램 "🤖 봄밤 알림봇 가동 시작!" 메시지 확인
4. `/run`으로 실동작 검증, 로그에서 `[브라우저] 실제 창 모드로 실행`(headless 아님) 확인

당일 자동 알림을 바로 테스트하려면: NAS `docker/bombam/work/settings.json`의
`last_run_date`를 `""`로 비우고 `/time`으로 몇 분 뒤 시각 설정.
