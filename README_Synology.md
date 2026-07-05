# Synology NAS 에서 Docker 로 돌리기 (Container Manager)

## 0. 사전 확인 — CPU 아키텍처
SSH 접속 후:
```bash
uname -m
```
- `x86_64` 또는 `aarch64` → ✅ 가능
- `armv7l` (저가형 일부) → ❌ Chromium 미지원, 불가

RAM은 **1GB 이상** 권장 (Chromium 한 개 ~300~500MB).

## 1. 폴더 준비
File Station 또는 SSH로 아래 구조를 만듭니다:
```
/volume1/docker/bombam/         ← 소스 전체(이 폴더 내용) 복사
/volume1/docker/bombam/profile/ ← 로그인 쿠키 둘 곳 (아래 3번)
/volume1/docker/bombam/work/    ← 결과 엑셀/JSON 이 떨어질 곳
```

## 2. 로그인 쿠키 준비 (가장 중요)
NAS엔 화면이 없어 직접 로그인 불가 → **내 맥에서 1회 로그인** 후 쿠키 폴더를 NAS로 복사:
```bash
# 맥에서 (창 떠서 로그인 → Enter)
HEADLESS=0 python3 2_작품별_최신댓글.py

# 생성된 쿠키를 NAS profile 폴더로 복사 (예: scp)
scp -r ~/.browser_data_dir/*  admin@NAS주소:/volume1/docker/bombam/profile/
```
> 쿠키 만료 시 이 단계만 다시.

## 3. Container Manager 에서 빌드/실행
### 방법 A — 프로젝트(GUI, 권장)
1. Container Manager → **프로젝트 → 생성**
2. 경로: `/volume1/docker/bombam`, 소스: 기존 `docker-compose.yml` 사용
3. **빌드 후 실행**

### 방법 B — SSH
```bash
cd /volume1/docker/bombam
sudo docker compose up --build
```

## 4. 결과 확인
`/volume1/docker/bombam/work/` 에 엑셀이 생성됩니다:
- `봄밤_작품별_최신댓글.xlsx` (기본 실행)
- 다른 작업은 compose의 `command:` 또는 Dockerfile `CMD` 를 바꿔서:
  - `python 1_전체수집.py` / `python 3_최근30일_댓글.py`

## 5. 매일 텔레그램 알림 (매일 11시)
오늘 기준 N일치(기본 2일) 새 댓글을 텔레그램으로 보냅니다.
1. `telegram.json` 에 봇토큰/챗ID 입력 (telegram.sample.json 참고)
2. 설정은 `ridi_collector.py` 상단: `NOTIFY_DAYS`(일수), `NOTIFY_WHEN_EMPTY`(빈날 발송)
3. DSM **제어판 → 작업 스케줄러 → 생성 → 예약된 작업 → 사용자 정의 스크립트**
   - 일정: **매일 11:00**
   - 명령:
     ```bash
     cd /volume1/docker/bombam && docker compose run --rm bombam python 4_매일알림.py
     ```

## 6. 그 밖의 주기 실행 (선택)
같은 방식으로 명령만 바꿔서 다른 작업도 예약 가능:
```bash
cd /volume1/docker/bombam && docker compose run --rm bombam python 3_최근30일_댓글.py
```

## 메모리 팁
- compose의 `shm_size: "1gb"`, `mem_limit: 1500m` 는 모델 RAM에 맞게 조정.
- 1GB 모델이면 `mem_limit` 를 800m 정도로 낮추고, 한 번에 한 스크립트만 실행.
- 코드에 `--disable-dev-shm-usage` 적용돼 있어 /dev/shm 작아도 동작.
