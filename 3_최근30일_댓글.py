#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[최근 30일 댓글]  최근 30일 동안 달린 댓글만 모아 → 최신순 엑셀

  실행:  python3 3_최근30일_댓글.py     ← 단독 실행 가능

  · 작품목록(봄밤_작품목록.json)이 있으면 그대로, 없으면 작가 페이지에서 먼저 받아옵니다.
  · 각 작품 전체 댓글을 받아 '최근 30일' 것만 골라 최신 댓글 순으로 정렬합니다.
  · 처음엔 Cloudflare·로그인 통과를 위해 '실제 창'으로 뜹니다. (자동 원하면 아래 "0"→"1")
  · 기간(일수)을 바꾸려면 ridi_collector.py 의 RECENT_DAYS 값을 수정하세요.

  결과:  봄밤_최근30일_댓글.xlsx   (번호 / 댓글 날짜 / 작품명(링크) / 작성자ID / 댓글 내용)
"""
import os

os.environ.setdefault("HEADLESS", "0")

from ridi_collector import run_recent_days

if __name__ == "__main__":
    run_recent_days()
