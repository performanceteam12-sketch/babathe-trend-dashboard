"""
주간 아카이브 — 매주 월요일 오전 10시(GitHub Actions, .github/workflows/weekly-archive.yml)에
실행되어 경쟁사 모니터링을 재수집하고, 그 주의 "NN년 N월 N주차" 라벨로 스냅샷을 기록하고,
슬랙으로 결과를 알린다 (영업회의 준비용).

**2026-09-04 스케줄 통합**: 원래는 금요일 10시(주간 아카이브, 이 스크립트)와 월요일 9시 30분
(monday_update.py, 최신 스냅샷만 갱신 + 슬랙 알림)로 나뉘어 있었다. 그런데 두 로컬 Windows 작업
스케줄러 작업 모두 등록 이후 단 한 번도 성공적으로 끝난 적이 없었다 — archive_weeks.csv를 실제로
커밋한 건 전체 기간 3건뿐이고 전부 수동/과거 세션에서 추가된 것, 자동 실행 자체의 커밋은 0건.
원인은 remote-refresh-watcher/keep-dashboard-awake와 같은 문제(PC 화면 잠금 시 Windows
스케줄러가 Playwright를 못 띄우는 오류 0x800710E0). 사용자 요청으로 두 작업을 월요일 오전 10시
GitHub Actions 1개로 합쳤다 — PC 상태와 무관하게 항상 실행되고, 스크래핑도 주 1회로 줄어든다
(저빈도 원칙에 더 부합). monday_update.py는 이 스크립트에 흡수되어 삭제됨.

브랜드검색/메타 소재 캡처 자체는 competitor_monitor_scraper.py의 run()을 그대로 재사용한다
(중복 구현 방지).

주차 계산: "그 달의 몇 번째 월요일인가"로 정의한다 (예: 8월의 첫 번째 월요일 = 1주차). 사용자가
기존에 Google Sheets에서 관리하던 "NN년 N월 N주차" 탭 이름 규칙과 동일하다. 실행일 자체가 항상
월요일이므로 라벨 계산에 별도 앵커링(요일 보정)이 필요 없지만, 수동 실행 등으로 실행일이
월요일이 아닐 경우를 대비해 `week_label_for()`가 그 주의 월요일로 보정해서 계산한다.

`archive_weeks.csv`의 `date` 컬럼은 실제 캡처(실행)일 그대로 저장한다 — competitor_monitor.csv에서
이미지를 조회할 때 쓰는 키와 일치해야 하기 때문이다.

슬랙 웹훅 URL: GitHub Actions에서는 리포지토리 시크릿 `SLACK_WEBHOOK_URL`(환경변수로 주입)을
먼저 확인하고, 없으면 로컬 `.streamlit/secrets.toml`의 `slack_webhook_url`을 본다(로컬에서 수동
실행할 때를 위해 유지). 대시보드 링크용 `DASHBOARD_URL`도 동일한 우선순위. 값이 없으면 알림을
건너뛰고 그 사실을 로그로 남긴다 — 조용히 실패하지 않는다.
"""

import json
import os
import sys
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib import request as urllib_request

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import competitor_monitor_scraper as cms  # noqa: E402
import git_sync  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_CSV = ROOT / "data" / "competitor_monitor" / "archive_weeks.csv"
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"


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


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)


def load_webhook_url() -> str | None:
    return os.environ.get("SLACK_WEBHOOK_URL") or load_secrets().get("slack_webhook_url")


def load_dashboard_url() -> str | None:
    return os.environ.get("DASHBOARD_URL") or load_secrets().get("dashboard_url")


def notify_slack(webhook_url: str, today: date, label: str, log: list) -> None:
    failures = [line for line in log if line.startswith("[FAIL]")]
    dashboard_url = load_dashboard_url()
    tag = f"<{dashboard_url}|[경쟁사 모니터링]>" if dashboard_url else "[경쟁사 모니터링]"
    if failures:
        summary = f"*{today.isoformat()} {label} {tag} 업데이트 중 {len(failures)}건 실패*"
        text = summary + "\n" + "\n".join(failures)
    else:
        text = f"*{today.isoformat()} {label} {tag} 업데이트 완료 (영업회의 준비 완료)*"
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib_request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
    urllib_request.urlopen(req, timeout=10)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    today = date.today()
    label = week_label_for(today)
    print(f"주간 아카이브 시작: {label} ({today.isoformat()})")

    log = cms.run(cms.BRANDS, today)
    record_archive(today, log)
    git_sync.sync_to_github(f"주간 아카이브: {label} ({today.isoformat()})", log)

    for line in log:
        print(line)

    webhook_url = load_webhook_url()
    if webhook_url:
        try:
            notify_slack(webhook_url, today, label, log)
            print("[OK] 슬랙 알림 발송 완료")
        except Exception as e:  # noqa: BLE001 — 슬랙 발송 실패는 전체 실행을 실패로 취급하지 않고 로그만 남긴다
            print(f"[FAIL] 슬랙 알림 발송 실패: {e}", file=sys.stderr)
    else:
        print(
            "[SKIP] SLACK_WEBHOOK_URL(Actions 시크릿) / slack_webhook_url(로컬 secrets.toml)이 "
            "설정되어 있지 않아 알림을 건너뜁니다.",
            file=sys.stderr,
        )

    failures = [l for l in log if l.startswith("[FAIL]")]
    if failures:
        print(f"\n{len(failures)}건 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
