#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[작품별 최신 댓글]  각 작품마다 가장 최신 댓글 1개(날짜+내용)만 수집 → 엑셀

  실행:  python3 2_작품별_최신댓글.py     ← 1번 없이 단독 실행 가능

  · 작품목록(봄밤_작품목록.json)이 있으면 그대로, 없으면 작가 페이지에서 먼저 받아옵니다.
  · '더보기'를 누르지 않고 첫 화면의 최신 댓글만 보므로 빠릅니다.
  · 처음엔 Cloudflare·로그인 통과를 위해 '실제 창'으로 뜹니다.
    (창 없이 자동 원하면 아래 "0"→"1")

  결과:  봄밤_작품별_최신댓글.xlsx   (번호 / 작품명 / 출간일 / 최신 댓글 날짜 / 내용 / URL)
"""
import os

os.environ.setdefault("HEADLESS", "0")

from ridi_collector import run_latest_only

if __name__ == "__main__":
    run_latest_only()
