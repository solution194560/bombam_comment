# 저사양 우분투 컨테이너에서 돌리기

## 1. 설치 (1회)
```bash
bash setup_ubuntu.sh
# 또는 수동:
pip3 install -r requirements.txt
python3 -m playwright install --with-deps chromium
```

## 2. 메모리 / 디스크
- **최소 RAM ≈ 1GB** 권장 (Chromium 1개 ~300~500MB). 512MB는 swap 없으면 위험.
- Docker 실행 시 `/dev/shm` 부족으로 죽는 일이 흔함 → 둘 중 하나:
  ```bash
  docker run --shm-size=1g ...
  # 또는
  docker run --ipc=host ...
  ```
  (코드에 `--disable-dev-shm-usage` 플래그는 이미 적용돼 있음)
- 디스크: Chromium ~400MB.

## 3. ⚠️ 가장 중요 — Cloudflare & 성인 로그인
서버(화면 없음)에서 headless로 처음 접속하면 **Cloudflare가 자주 막고, 성인 콘텐츠는 로그인 쿠키가 필요**합니다.
화면이 없으니 컨테이너 안에서 직접 로그인할 수 없습니다. **두 가지 방법** 중 택1:

### 방법 A (권장) — 로컬에서 로그인한 쿠키를 복사
1. 내 PC(맥/윈도)에서 한 번 실제 창으로 로그인:
   ```bash
   HEADLESS=0 python3 2_작품별_최신댓글.py   # 창에서 로그인 후 Enter
   ```
2. 생성된 프로필 폴더 `~/.browser_data_dir` 를 컨테이너로 복사:
   ```bash
   # 예시
   docker cp ~/.browser_data_dir  <컨테이너>:/root/.browser_data_dir
   # 또는 scp / 볼륨 마운트
   ```
3. 컨테이너에서는 headless로 그대로 실행:
   ```bash
   HEADLESS=1 BROWSER_PROFILE=/root/.browser_data_dir python3 2_작품별_최신댓글.py
   ```
   > 쿠키 만료(수 주~수 개월) 시 1번 단계만 다시.

### 방법 B — 컨테이너에서 가상 디스플레이(xvfb)로 헤드풀 로그인
```bash
sudo apt-get install -y xvfb
xvfb-run -a env HEADLESS=0 python3 2_작품별_최신댓글.py
```
화면이 없어 로그인 입력이 어려우므로 **방법 A가 훨씬 쉽습니다.**

## 4. 실행
```bash
HEADLESS=1 python3 1_전체수집.py        # 전체
HEADLESS=1 python3 2_작품별_최신댓글.py  # 작품별 최신댓글
HEADLESS=1 python3 3_최근30일_댓글.py    # 최근 30일
```

## 5. 정리
- 작가/주소: `ridi_collector.py` 상단 변수
- 계정: `account.json`
- 프로필 경로: 환경변수 `BROWSER_PROFILE`
