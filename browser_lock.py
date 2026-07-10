# 프로세스 간 브라우저 동시 실행 방지 락 — 2GB RAM에서 Chromium 2개 동시 구동을 막는다 (mkdir 원자 연산)
import os
import time
import shutil
from datetime import datetime

LOCK_DIR = os.path.join(os.environ.get("OUTPUT_DIR", "."), "browser.lock")
STALE_SEC = 4500   # 75분 — 리디 수집 subprocess timeout(3600초)보다 길게


def _log(msg):
    print(f"[락] {msg}", flush=True)


def acquire(owner: str, wait_sec: int, interval: int = 30) -> bool:
    """os.mkdir 원자 획득. 성공 시 소유자 정보를 기록하고 True 반환.
       실패 시 interval초 간격으로 wait_sec까지 재시도. STALE_SEC 초과한 락은 크래시
       잔재로 보고 제거 후 재획득. 끝내 못 잡으면 False."""
    waited = 0
    announced = False
    while True:
        try:
            os.mkdir(LOCK_DIR)
            # 획득 성공 — 소유자·pid·시각 기록(디버깅용, 실패해도 락 자체는 유효)
            try:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(os.path.join(LOCK_DIR, "owner.txt"), "w", encoding="utf-8") as f:
                    f.write(f"{owner} pid={os.getpid()} {stamp}\n")
            except Exception:
                pass
            _log(f"'{owner}' 락 획득")
            return True
        except FileExistsError:
            # 이미 누군가 점유 중 — stale 여부 확인
            try:
                age = time.time() - os.path.getmtime(LOCK_DIR)
            except OSError:
                age = 0
            if age > STALE_SEC:
                _log(f"stale 락 감지({age:.0f}초 경과) — 제거 후 재획득 시도")
                shutil.rmtree(LOCK_DIR, ignore_errors=True)
                continue
            if waited >= wait_sec:
                _log(f"'{owner}' 락 획득 포기 — {wait_sec}초 대기 초과")
                return False
            if not announced:
                _log(f"'{owner}' 다른 프로세스가 브라우저 사용 중 — 최대 {wait_sec}초 대기 시작")
                announced = True
            time.sleep(interval)
            waited += interval


def release() -> None:
    """락 디렉토리 제거. 이미 없어도 무해."""
    shutil.rmtree(LOCK_DIR, ignore_errors=True)
