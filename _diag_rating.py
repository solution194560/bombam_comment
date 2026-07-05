#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[진단용] 리디북스 리뷰 li 의 구조를 덤프해서 '구매자 평점'이 DOM 어디에 있는지 확인.
   결과는 /app/out/_diag_rating.txt 로 저장(마운트된 work 폴더). 일회성 스크립트."""
import os, time, json
os.environ.setdefault("HEADLESS", "0")
import ridi_collector as rc
from playwright.sync_api import sync_playwright

# 댓글이 많은 작품으로 조사 (짖어봐, 암캐 - 21개)
BOOK_URL = "https://ridibooks.com/books/4287000159"

DUMP_JS = r"""
() => {
  const sec = document.querySelector('#ISLANDS__Review') ||
              document.querySelector('#detail_review');
  if (!sec) return {err: 'no review section'};
  const out = [];
  let count = 0;
  for (const li of sec.querySelectorAll('li')) {
    const txt = (li.innerText || '');
    if (!/\d{4}\.\d{2}\.\d{2}/.test(txt)) continue;
    if (!/\*\*\*/.test(txt)) continue;
    count++;
    if (count > 8) break;
    // 별 아이콘: viewBox 0 0 48 48 인 svg (첫 진단에서 확인)
    const svgs = [...li.querySelectorAll('svg')].filter(s => s.getAttribute('viewBox') === '0 0 48 48');
    const stars = svgs.map(s => {
      const cs = getComputedStyle(s);
      return { cls: s.getAttribute('class')||'', color: cs.color, fill: cs.fill };
    });
    out.push({ text: txt.slice(0, 22), n_stars: svgs.length, stars });
  }
  return {count_found: count, samples: out};
}
"""

with sync_playwright() as p:
    b = rc._new_browser(p)
    page = b.new_page()
    rc._try_login(page)
    rc._open_book_and_scroll(page, BOOK_URL)
    time.sleep(2)
    data = page.evaluate(DUMP_JS)
    b.close()

out_path = "/app/out/_diag_rating.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(json.dumps(data, ensure_ascii=False, indent=2))
print("=== 진단 결과 저장:", out_path, "===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
