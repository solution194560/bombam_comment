#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[매일 알림]  오늘 기준 N일치 새 댓글을 수집해 텔레그램으로 전송

  실행:  python3 4_매일알림.py
  예약:  시놀로지 작업 스케줄러에서 매일 11:00 에 실행 (DAILY_TIME 참고)

  설정(ridi_collector.py 상단):
    AUTHOR            작가
    NOTIFY_DAYS       오늘 기준 며칠치 댓글을 볼지 (기본 2)
    NOTIFY_WHEN_EMPTY 새 댓글 없을 때도 보낼지 (기본 False = 있을 때만)
  텔레그램 계정: telegram.json
"""
import os

os.environ.setdefault("HEADLESS", "0")   # 컨테이너에선 HEADLESS=1 로 override

from ridi_collector import gather_recent, format_notify_message, NOTIFY_DAYS, NOTIFY_WHEN_EMPTY, load_settings
from notify import notify_telegram, _load_telegram

def _resolve_recipients():
    """이 실행에서 알림을 보낼 수신자 chat_id 목록을 정한다.
       자동(TELEGRAM_AUTO=1)이면 구독자 전원(+소유자), 수동이면 TELEGRAM_CHAT_ID 한 명."""
    if os.environ.get("TELEGRAM_AUTO") == "1":
        ids = [str(x).strip() for x in (load_settings().get("subscribers") or []) if str(x).strip()]
        owner = str(_load_telegram()["chat_id"] or "")
        if owner and owner not in ids:
            ids.append(owner)
        return ids
    cid = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return [cid] if cid else []


if __name__ == "__main__":
    rows, _, stats = gather_recent(NOTIFY_DAYS)

    print(f"수집 통계: {stats['succeeded']}/{stats['total']} 성공"
          f"{'(조기 중단)' if stats['aborted'] else ''}")

    # 수정 3: 전면 실패 / 조기 중단 시 '⚠️ 수집 실패' 알림
    #  · 전면 실패: 조기 중단이면서 성공 0개 (또는 실패만 있고 성공 0개)
    #  · 조기 중단(일부 수집): aborted 이지만 일부는 수집됨 → 알림 + 이하 정상 전송 계속
    fail_msg = None
    partial_abort = False
    if (stats["aborted"] and stats["succeeded"] == 0) or \
       (stats["failed"] > 0 and stats["succeeded"] == 0):
        # 전면 실패
        fail_msg = (f"⚠️ 수집 실패\n\n"
                    f"작품 {stats['total']}개 중 {stats['failed']}개 접속 실패\n"
                    f"(네트워크 문제 추정)\n\n"
                    f"나중에 /run 명령으로 다시 시도해 주세요.")
    elif stats["aborted"]:
        # 조기 중단 (일부만 수집됨)
        partial_abort = True
        fail_msg = (f"⚠️ 수집 조기 중단\n\n"
                    f"작품 {stats['total']}개 중 {stats['succeeded']}개만 수집됨\n"
                    f"(네트워크 문제로 추정)\n\n"
                    f"현재까지 수집한 댓글을 이하 전송합니다.")

    if fail_msg:
        recipients = _resolve_recipients()
        for cid in recipients:
            notify_telegram(fail_msg, chat_id=cid)
        print(f"수집 실패 알림 전송: {len(recipients)}명")

    # 전면 실패면 정상 알림 로직으로 넘어가지 않음 (조기 중단이라도 일부 수집됐으면 계속 전송)
    if fail_msg and not partial_abort:
        pass
    elif rows or NOTIFY_WHEN_EMPTY:
        msg = format_notify_message(rows, NOTIFY_DAYS)
        # 매일 자동 실행(bot.py가 TELEGRAM_AUTO=1)이면 구독자 전원에게,
        # 수동 /run(TELEGRAM_CHAT_ID 단일)이면 그 사람에게만.
        # 자동일 때는 '지금 이 순간' settings.json 을 새로 읽어 수신자를 정한다
        # (수집이 도는 몇 분 사이에 등록한 사람도 그날 알림을 받도록).
        if os.environ.get("TELEGRAM_AUTO") == "1":
            ids = [str(x).strip() for x in (load_settings().get("subscribers") or []) if str(x).strip()]
            owner = str(_load_telegram()["chat_id"] or "")
            if owner and owner not in ids:
                ids.append(owner)
            results = {cid: notify_telegram(msg, chat_id=cid) for cid in ids}
            n_ok = sum(results.values())
            print(f"\n알림 전송: {n_ok}/{len(ids)}명 성공 | 새 댓글 {len(rows)}건")
            for cid, sent in results.items():
                if not sent:
                    print(f"  ⚠️  {cid} 전송 실패(탈퇴/차단 등) → subscribers 에서 정리 필요할 수 있음")
        else:
            ok = notify_telegram(msg)
            print(f"\n알림 {'전송 완료' if ok else '전송 실패/생략'} | 새 댓글 {len(rows)}건")
    else:
        print(f"\n새 댓글 없음 → 알림 보내지 않음 (NOTIFY_WHEN_EMPTY=False)")
