#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[전체 수집]  작가 페이지 → 작품목록 → 각 작품 전체댓글 → 엑셀

  실행:  python3 1_전체수집.py
  설정:  작가/주소/계정은 ridi_collector.py 상단 + account.json 에서 관리
"""
import os

# 첫 실행은 Cloudflare 인증·로그인 통과를 위해 '실제 창'으로 뜹니다.
#   → 한 번 통과하면 쿠키가 저장돼 다음부턴 창 없이도 됩니다.
#   → 창 없이(자동) 돌리려면 아래 "0" 을 "1" 로 바꾸세요.
os.environ.setdefault("HEADLESS", "0")

from ridi_collector import run_full

if __name__ == "__main__":
    run_full()
