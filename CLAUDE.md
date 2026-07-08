# 봄밤 텔레그램 알림봇 프로젝트

리디북스 작가 "봄밤"(author_url: `https://ridibooks.com/author/117346`)의 작품·댓글을
Playwright로 스크래핑해서, 매일 정해진 시각에 최근 N일 새 댓글을 텔레그램으로 알려주는 시스템.
시놀로지 NAS(DS224+, Celeron J4125, RAM 2GB)에서 Docker 컨테이너로 24시간 상주 운영.

## 작업 워크플로우 (반드시 준수)

**모든 코드/설정 변경은 이 순서로 진행한다:**
1. **작업 전 리뷰** — 무엇을, 왜 바꾸는지 먼저 설명하고 사용자 확인을 받는다.
2. **로컬 Docker 테스트** — `docker build` + `docker run`으로 실제 컨테이너에서 해당 시나리오를
   통과시킨다. 절대 추측만으로 NAS를 고치려 하지 않는다.
3. **통과했을 때만** `main`에 push하고 NAS에서 `봄밤_배포`를 실행한다(git 반자동 배포,
   상세는 "시놀로지 배포 절차"). 레거시 zip 방식은 백업 경로.

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
12. **`.dockerignore`는 ASCII만.** 한글 파일명·주석이 들어가면 CLI 빌드(`docker compose`,
    buildkit)가 `exclude-patterns` 헤더에 비-ASCII를 넣다가 `non-printable ASCII characters`로
    build context 로드에서 실패한다. Container Manager GUI 빌드는 관대해 통과하지만 NAS
    git 반자동 배포는 CLI라 터진다. 한글 파일 제외가 필요하면 `README_*.md`처럼 ASCII 글롭 사용.
13. **작품목록 캐시는 '개수'만이 아니라 '제목 품질'도 검증해야 한다.** 작가 페이지에는 책 하나당
    앵커가 여러 개("상세페이지 바로가기" 등 접근성/버튼 텍스트 포함) 있어, 첫 앵커를 무차별
    채택하면 쓰레기 제목이 book_id를 선점해 캐시로 굳는다(함정 6번의 '품질판' 재발). `WORKS_JS`는
    나쁜 제목 앵커를 book_id 소비 없이 스킵하고, `_load_or_collect_works`/`collect_work_list`는
    `_good_title()`로 걸러 자동 정화한다(로드한 오염 캐시는 정상 절반 이상이면 정화 후 재저장,
    미만이면 재수집). 실패 로그에 "상세페이지 바로가기 | ❌ Page.goto: Timeout"이 보이면 이 오염을
    의심할 것.

## 로컬 테스트 실행법

```bash
cd "/Users/hyundeok/Downloads/봄밤작가 작품 리스트와 댓글 평가-3/"
docker stop bombam_test 2>&1; docker rm bombam_test 2>&1   # 기존 컨테이너 정리
rm -f local_test/profile/Singleton*                          # 잔여 락 정리
docker build -t bombam:test .
docker run -d --name bombam_test --shm-size=1gb \
  -e HEADLESS=0 \
  --env-file local_test/telegram_test.env \
  -v "$(pwd)/local_test/profile:/app/.browser_data_dir" \
  -v "$(pwd)/local_test/work:/app/out" \
  bombam:test
docker logs -f bombam_test          # 실시간 로그 확인
```

**로컬 테스트는 반드시 `--env-file local_test/telegram_test.env`를 붙인다.** 이 파일(git 제외)에
테스트 전용 봇(`@bombam_publish_STG_bot`)의 `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`가 들어 있고,
notify.py가 환경변수를 telegram.json보다 우선하므로 NAS 운영 봇과 폴링이 분리된다
(`409 Conflict` 없음). env-file 없이 띄우면 이미지에 COPY된 telegram.json의 **운영 봇**으로
폴링해 NAS와 충돌하니 금지. 테스트 결과 메시지는 테스트 봇 대화방으로 온다.

## 시놀로지 배포 절차

**git 반자동 배포(현행 표준).** 로컬 검증 후 `main`에 push하면, NAS에서 버튼 하나로 배포한다.

전제(1회 구성 완료됨): NAS `/volume1/docker/bombam`는 GitHub `solution194560/bombam_comment`
(**비공개**)의 git 작업본이며, 읽기전용 fine-grained 토큰이 `.git/config`에 저장돼 있다(root 전용).
DSM 작업 스케줄러의 `봄밤_배포`(root 실행) 작업이 `docker run alpine/git`로 `origin/main`을
`reset --hard`해 받아온 뒤 `docker compose -p bombam ... up -d --build`로 빌드·재시작하고
`docker image prune -f`로 청소까지 한다(호스트에 git 미설치 → 컨테이너 git 사용). 배포 기준은 `main`.

1. (맥) 코드 수정 → **로컬 Docker 빌드/실행 테스트(필수)** → `main`에 반영(commit+push)
2. (NAS) 작업 스케줄러 → **`봄밤_배포` → 실행** (git pull + build + up -d + prune)
3. 텔레그램 "🤖 봄밤 알림봇 가동 시작!" 확인 → `bombam` 컨테이너가 **하나만** `Up`
4. `/run`으로 실동작 검증, 로그에서 `[브라우저] 실제 창 모드로 실행`(headless 아님) 확인

민감 파일(account.json/telegram.json 등)은 `.gitignore`라 pull이 건드리지 않고 NAS 폴더에 상주한다.
`봄밤_배포`는 빌드 전 이 파일들의 존재를 확인하고, 없으면 로그인 실패 방지를 위해 중단한다.
compose 프로젝트명이 폴더명(`bombam`)과 같아 CLI 빌드해도 Container Manager와 같은 스택을 갱신한다
(중복 컨테이너 안 생김).

**레거시(수동 zip) 방식** — git 경로가 막힐 때의 백업으로만: File Station으로 `bombam_synology.zip`
덮어쓰기 업로드 → 압축풀기 → Container Manager에서 **다시 빌드**.

당일 자동 알림을 바로 테스트하려면: NAS `docker/bombam/work/settings.json`의
`last_run_date`를 `""`로 비우고 `/time`으로 몇 분 뒤 시각 설정.
