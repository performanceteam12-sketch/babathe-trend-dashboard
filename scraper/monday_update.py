"""
월요일 업데이트 — 매주 월요일 오전 9시 30분에 실행되어 영업회의 전에 경쟁사 모니터링
(브랜드검색+메타소재)을 최신화하고, 완료되면 슬랙으로 알린다.

브랜드검색/메타 소재 캡처는 competitor_monitor_scraper.py의 run()을 그대로 재사용한다
(주간 아카이브(weekly_archive.py, 금요일 실행)와 동일한 패턴 — 중복 구현 방지).
이 스크립트는 주차 라벨을 기록하지 않는다(그건 금요일 아카이브의 역할) — 그냥 그날그날의
"최신" 스냅샷만 갱신해 회의 시작 전 대시보드가 최신 상태이도록 하는 것이 목적이다.

슬랙 웹훅 URL은 .streamlit/secrets.toml의 `slack_webhook_url` 키에서 읽는다
(이 파일은 프로젝트 .gitignore에 이미 포함되어 있어 커밋되지 않는다). 값이 없으면 알림을
건너뛰고 그 사실을 로그로 남긴다 — 조용히 실패하지 않는다.
"""

import json
import sys
import tomllib
from datetime import date
from pathlib import Path
from urllib import request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import competitor_monitor_scraper as cms  # noqa: E402
import git_sync  # noqa: E402

SECRETS_PATH = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)


def load_webhook_url() -> str | None:
    return load_secrets().get("slack_webhook_url")


def load_dashboard_url() -> str | None:
    # 대시보드가 배포되면 .streamlit/secrets.toml에 dashboard_url을 추가해 링크를 걸 수 있게 한다.
    return load_secrets().get("dashboard_url")


def notify_slack(webhook_url: str, today: date, log: list) -> None:
    # "@babafashion"은 실제 슬랙 멘션(알림 발송)이 아니라 굵은 텍스트로만 표시한다 (사용자 요청).
    failures = [line for line in log if line.startswith("[FAIL]")]
    dashboard_url = load_dashboard_url()
    label = f"<{dashboard_url}|[경쟁사 모니터링]>" if dashboard_url else "[경쟁사 모니터링]"
    tag = "*@babafashion*"
    if failures:
        text = (
            f"{today.isoformat()} {label} 업데이트 중 {len(failures)}건 실패 {tag}\n"
            + "\n".join(failures)
        )
    else:
        text = f"{today.isoformat()} {label} 업데이트 완료 {tag}"
    body = json.dumps({"text": text}).encode("utf-8")
    req = request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
    request.urlopen(req, timeout=10)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    today = date.today()
    print(f"월요일 업데이트 시작: {today.isoformat()}")

    log = cms.run(cms.BRANDS, today)
    git_sync.sync_to_github(f"월요일 업데이트: {today.isoformat()}", log)
    for line in log:
        print(line)

    webhook_url = load_webhook_url()
    if webhook_url:
        try:
            notify_slack(webhook_url, today, log)
            print("[OK] 슬랙 알림 발송 완료")
        except Exception as e:  # noqa: BLE001 — 슬랙 발송 실패는 전체 업데이트를 실패로 취급하지 않고 로그만 남긴다
            print(f"[FAIL] 슬랙 알림 발송 실패: {e}", file=sys.stderr)
    else:
        print(
            "[SKIP] slack_webhook_url이 .streamlit/secrets.toml에 설정되어 있지 않아 알림을 건너뜁니다.",
            file=sys.stderr,
        )

    failures = [line for line in log if line.startswith("[FAIL]")]
    if failures:
        print(f"\n{len(failures)}건 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
