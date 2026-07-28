"""
주간 아카이브 — 매주 금요일 오전 10시에 실행되어 그 주의 경쟁사 모니터링 스냅샷을
"NN년 N월 N주차" 라벨로 기록한다.

브랜드검색/메타 소재 캡처 자체는 competitor_monitor_scraper.py의 run()을 그대로 재사용한다
(중복 구현 방지). 이 스크립트가 추가로 하는 일은 실행 시점의 날짜에 해당하는 "주차 라벨"을
계산해서 data/competitor_monitor/archive_weeks.csv에 기록하는 것뿐이다.

주차 계산: "그 달의 몇 번째 월요일인가"로 정의한다 (예: 8월의 첫 번째 월요일 = 1주차). 사용자가
기존에 Google Sheets에서 관리하던 "NN년 N월 N주차" 탭 이름 규칙과 동일하다.

라벨은 실행일(금요일) 자체가 아니라 **그 주의 월요일**을 기준으로 계산한다(`week_label_for()`).
그래야 실행 요일이 바뀌어도(예: 공휴일로 하루 밀려서 목/토에 수동 실행) 같은 주차로 라벨링되고,
드물게 한 주가 월 경계를 넘는 경우(월요일이 그 달 마지막 날인 주)도 올바르게 처리된다.
반면 `archive_weeks.csv`의 `date` 컬럼은 실제 캡처(실행)일 그대로 저장한다 —
`competitor_monitor.csv`에서 이미지를 조회할 때 쓰는 키와 일치해야 하기 때문이다.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import competitor_monitor_scraper as cms  # noqa: E402

ARCHIVE_CSV = Path(__file__).resolve().parent.parent / "data" / "competitor_monitor" / "archive_weeks.csv"


def week_of_month(d: date) -> int:
    count = 0
    for day in range(1, d.day + 1):
        if d.replace(day=day).weekday() == 0:  # 월요일
            count += 1
    return max(count, 1)


def week_label(d: date) -> str:
    yy = d.year % 100
    return f"{yy}년 {d.month}월 {week_of_month(d)}주차"


def week_label_for(d: date) -> str:
    # dashboard/app.py의 week_label()과 동일한 계산을 쓰되, 실행일이 아니라 그 주의 월요일을 기준으로 앵커링한다.
    monday = d - timedelta(days=d.weekday())
    return week_label(monday)


def record_archive(d: date, log: list):
    label = week_label_for(d)
    ARCHIVE_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        pd.read_csv(ARCHIVE_CSV, encoding="utf-8-sig", keep_default_na=False)
        if ARCHIVE_CSV.exists()
        else pd.DataFrame(columns=["week_label", "date", "archived_at"])
    )
    existing = existing[existing["week_label"] != label]
    new_row = pd.DataFrame([{
        "week_label": label,
        "date": d.isoformat(),
        "archived_at": datetime.now().isoformat(timespec="seconds"),
    }])
    combined = pd.concat([existing, new_row], ignore_index=True)
    combined.to_csv(ARCHIVE_CSV, index=False, encoding="utf-8-sig")
    log.append(f"[OK] 주간 아카이브 기록: {label} -> {d.isoformat()}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    today = date.today()
    label = week_label_for(today)
    print(f"주간 아카이브 시작: {label} ({today.isoformat()})")

    log = cms.run(cms.BRANDS, today)
    record_archive(today, log)

    for line in log:
        print(line)

    failures = [l for l in log if l.startswith("[FAIL]")]
    if failures:
        print(f"\n{len(failures)}건 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
